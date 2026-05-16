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

SUSPECT_THRESHOLD = 1
OFFLINE_THRESHOLD = 3
RECOVER_THRESHOLD = 2
SHUTDOWN_AUTO_RECOVER = True

NON_READY_STATES = ("shutdown", "startup", "disconnected", "error")


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
            settings = get_settings()
            await asyncio.sleep(settings.heartbeat_interval)

    async def _check_all(self):
        settings = get_settings()
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.heartbeat_max_concurrent)
        self._heartbeat_round += 1

        async with async_session() as db:
            result = await db.execute(select(Device))
            devices = result.scalars().all()

            tasks = []
            for dev in devices:
                client = self._clients.get(dev.id)
                if not client:
                    continue
                if (dev.status == DeviceStatus.OFFLINE
                        and dev.missed_heartbeats >= OFFLINE_THRESHOLD
                        and self._heartbeat_round % settings.heartbeat_offline_skip_rounds != 0):
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
        async with self._semaphore:
            await self._check_one(db, dev, client)

    async def _check_one(self, db: AsyncSession, dev: Device, client: MoonrakerClient):
        if dev.status == DeviceStatus.ESTOP:
            return

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

            if SHUTDOWN_AUTO_RECOVER and dev.status in (DeviceStatus.ONLINE, DeviceStatus.RECOVERING):
                klippy_state = await client.get_klippy_state()
                if klippy_state == "ready":
                    if dev.status == DeviceStatus.RECOVERING:
                        dev.status = DeviceStatus.ONLINE
                        self._recover_count.pop(dev.id, None)
                elif klippy_state in NON_READY_STATES:
                    client.invalidate_ready_cache()
                    logger.warning(
                        "Device %d (%s) MCU state=%s detected in heartbeat, marking SUSPECT (recovery deferred to operation)",
                        dev.id, dev.ip, klippy_state,
                    )
                    dev.status = DeviceStatus.SUSPECT
                    await ws_manager.broadcast("device_status", {
                        "device_id": dev.id,
                        "ip": dev.ip,
                        "status": f"MCU_{klippy_state.upper()}",
                        "message": f"MCU {klippy_state} detected, recovery deferred to next operation",
                    })
        else:
            dev.missed_heartbeats += 1
            self._recover_count.pop(dev.id, None)
            client.invalidate_ready_cache()
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
            if not dev or dev.status != DeviceStatus.ESTOP:
                return
            client = self._clients.get(dev.id)
            if client:
                try:
                    await client.firmware_restart()
                    logger.info("Firmware restart sent to device %d (%s)", dev.id, dev.ip)
                except Exception as e:
                    logger.error("Firmware restart failed for device %d (%s): %s", dev.id, dev.ip, e)
            dev.status = DeviceStatus.RECOVERING
            dev.missed_heartbeats = 0
            self._recover_count[dev.id] = 0
            await db.commit()
            await ws_manager.broadcast("device_status", {
                "device_id": dev.id, "status": "RECOVERING",
            })

    async def reset_all(self):
        async with async_session() as db:
            result = await db.execute(select(Device).where(Device.status == DeviceStatus.ESTOP))
            devices = result.scalars().all()
            for dev in devices:
                client = self._clients.get(dev.id)
                if client:
                    try:
                        await client.firmware_restart()
                        logger.info("Firmware restart sent to device %d (%s)", dev.id, dev.ip)
                    except Exception as e:
                        logger.error("Firmware restart failed for device %d (%s): %s", dev.id, dev.ip, e)
                dev.status = DeviceStatus.RECOVERING
                dev.missed_heartbeats = 0
                self._recover_count[dev.id] = 0
            await db.commit()
        if devices:
            await ws_manager.broadcast("emergency_reset", {"count": len(devices)})
            logger.info("Reset %d devices from ESTOP (firmware_restart sent)", len(devices))


device_manager = DeviceManager()
