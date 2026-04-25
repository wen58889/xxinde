from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.device import Device, DeviceStatus
from app.services.moonraker_client import MoonrakerClient
from app.ws_manager import ws_manager
from app.config import get_settings

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10  # seconds (was 5, too aggressive for 100+ devices)
SUSPECT_THRESHOLD = 1    # missed heartbeats to become SUSPECT
OFFLINE_THRESHOLD = 3    # missed heartbeats to become OFFLINE
RECOVER_THRESHOLD = 2    # consecutive successes to recover
MAX_CONCURRENT_CHECKS = 15  # 最多15台设备同时探测，避免连接风暴
OFFLINE_CHECK_INTERVAL = 6  # 已确认离线的设备每6轮才检查1次（≈60s）


class DeviceManager:
    def __init__(self):
        self._clients: dict[int, MoonrakerClient] = {}
        self._task: asyncio.Task | None = None
        self._recover_count: dict[int, int] = {}
        self._heartbeat_round: int = 0
        self._semaphore: asyncio.Semaphore | None = None

    def get_client(self, device_id: int) -> MoonrakerClient | None:
        return self._clients.get(device_id)

    async def init_devices(self):
        """加载已有设备并为其创建 MoonrakerClient。
        不再自动批量创建幽灵设备——设备只通过扫描发现后入库。
        """
        settings = get_settings()
        async with async_session() as db:
            result = await db.execute(select(Device))
            devices = result.scalars().all()

            for dev in devices:
                self._clients[dev.id] = MoonrakerClient(
                    dev.ip, settings.device_moonraker_port
                )
            logger.info("Loaded %d existing devices", len(self._clients))

    async def start_heartbeat(self):
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Heartbeat loop started")

    async def stop_heartbeat(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self):
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.error("Heartbeat error: %s", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _check_all(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
        self._heartbeat_round += 1

        async with async_session() as db:
            result = await db.execute(select(Device))
            devices = result.scalars().all()

            tasks = []
            for dev in devices:
                client = self._clients.get(dev.id)
                if not client:
                    continue
                # 已确认离线的设备降频检查（每 OFFLINE_CHECK_INTERVAL 轮一次）
                if (dev.status == DeviceStatus.OFFLINE
                        and dev.missed_heartbeats >= OFFLINE_THRESHOLD
                        and self._heartbeat_round % OFFLINE_CHECK_INTERVAL != 0):
                    continue
                tasks.append(self._check_one_throttled(db, dev, client))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await db.commit()
            skipped = len(devices) - len(tasks)
            if skipped > 0:
                logger.debug("Heartbeat #%d: checked %d, skipped %d offline",
                             self._heartbeat_round, len(tasks), skipped)

    async def _check_one_throttled(self, db: AsyncSession, dev: Device, client: MoonrakerClient):
        """带并发限制的单设备检查"""
        async with self._semaphore:
            await self._check_one(db, dev, client)

    async def _check_one(self, db: AsyncSession, dev: Device, client: MoonrakerClient):
        if dev.status == DeviceStatus.ESTOP:
            return  # Skip ESTOP devices

        alive = await client.is_alive()
        now = datetime.now(timezone.utc)
        old_status = dev.status

        if alive:
            dev.last_heartbeat = now
            dev.missed_heartbeats = 0
            if dev.status in (DeviceStatus.OFFLINE, DeviceStatus.SUSPECT):
                dev.status = DeviceStatus.RECOVERING
                self._recover_count[dev.id] = 1
            elif dev.status == DeviceStatus.RECOVERING:
                self._recover_count[dev.id] = self._recover_count.get(dev.id, 0) + 1
                if self._recover_count[dev.id] >= RECOVER_THRESHOLD:
                    dev.status = DeviceStatus.ONLINE
                    self._recover_count.pop(dev.id, None)
            else:
                dev.status = DeviceStatus.ONLINE
        else:
            dev.missed_heartbeats += 1
            self._recover_count.pop(dev.id, None)
            if dev.missed_heartbeats >= OFFLINE_THRESHOLD:
                dev.status = DeviceStatus.OFFLINE
            elif dev.missed_heartbeats >= SUSPECT_THRESHOLD:
                dev.status = DeviceStatus.SUSPECT

        if dev.status != old_status:
            logger.info("Device %d (%s): %s → %s", dev.id, dev.ip, old_status, dev.status)
            await ws_manager.broadcast("device_status", {
                "device_id": dev.id,
                "ip": dev.ip,
                "status": dev.status.value,
            })

    async def set_estop(self, device_id: int):
        async with async_session() as db:
            result = await db.execute(select(Device).where(Device.id == device_id))
            dev = result.scalar_one_or_none()
            if dev:
                client = self._clients.get(dev.id)
                if client:
                    try:
                        await client.emergency_stop()
                    except Exception as e:
                        logger.error("ESTOP send failed for %s: %s", dev.ip, e)
                dev.status = DeviceStatus.ESTOP
                await db.commit()
                await ws_manager.broadcast("device_status", {
                    "device_id": dev.id, "status": "ESTOP",
                })

    async def set_estop_all(self):
        async with async_session() as db:
            result = await db.execute(select(Device))
            for dev in result.scalars().all():
                client = self._clients.get(dev.id)
                if client:
                    try:
                        await client.emergency_stop()
                    except Exception:
                        pass
                dev.status = DeviceStatus.ESTOP
            await db.commit()
        await ws_manager.broadcast("emergency_stop", {"all": True})

    async def reset_device(self, device_id: int):
        async with async_session() as db:
            result = await db.execute(select(Device).where(Device.id == device_id))
            dev = result.scalar_one_or_none()
            if dev and dev.status == DeviceStatus.ESTOP:
                dev.status = DeviceStatus.OFFLINE
                dev.missed_heartbeats = 0
                await db.commit()

    async def reset_all(self):
        """Reset all ESTOP devices so heartbeat can re-evaluate their status."""
        async with async_session() as db:
            result = await db.execute(select(Device).where(Device.status == DeviceStatus.ESTOP))
            devices = result.scalars().all()
            for dev in devices:
                dev.status = DeviceStatus.OFFLINE
                dev.missed_heartbeats = 0
            await db.commit()
        if devices:
            await ws_manager.broadcast("emergency_reset", {"count": len(devices)})
            logger.info("Reset %d devices from ESTOP", len(devices))


device_manager = DeviceManager()
