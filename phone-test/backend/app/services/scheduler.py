from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from app.database import async_session
from app.models.task import TaskExecution, TaskStatus
from app.models.device import Device, DeviceStatus
from app.services.device_manager import device_manager
from app.services.device_lock import device_lock_manager
from app.services.flow_engine import FlowEngine
from app.services.coordinate import CoordinateMapper
from app.ws_manager import ws_manager

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 22


class Scheduler:
    def __init__(self):
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._running_engines: dict[int, FlowEngine] = {}

    async def dispatch_task(self, device_id: int, yaml_content: str) -> int:
        async with async_session() as db:
            # Verify device is ONLINE
            result = await db.execute(select(Device).where(Device.id == device_id))
            dev = result.scalar_one_or_none()
            if not dev:
                raise ValueError(f"Device {device_id} not found")
            if dev.status != DeviceStatus.ONLINE:
                raise ValueError(f"Device {device_id} is {dev.status.value}, not ONLINE")

            # Create task record
            task = TaskExecution(
                device_id=device_id,
                status=TaskStatus.PENDING,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            task_id = task.id

        # Run in background
        asyncio.create_task(self._run_task(device_id, task_id, yaml_content))
        return task_id

    async def _run_task(self, device_id: int, task_id: int, yaml_content: str):
        acquired = await device_lock_manager.acquire(device_id, task_id)
        if not acquired:
            async with async_session() as db:
                result = await db.execute(
                    select(TaskExecution).where(TaskExecution.id == task_id)
                )
                task = result.scalar_one()
                task.status = TaskStatus.FAILED
                task.error = "Failed to acquire device lock"
                await db.commit()
            return

        try:
            async with self._semaphore:
                await self._execute(device_id, task_id, yaml_content)
        finally:
            device_lock_manager.release(device_id, task_id)
            self._running_engines.pop(device_id, None)

    async def _execute(self, device_id: int, task_id: int, yaml_content: str):
        async with async_session() as db:
            result = await db.execute(select(Device).where(Device.id == device_id))
            dev = result.scalar_one()

            result = await db.execute(
                select(TaskExecution).where(TaskExecution.id == task_id)
            )
            task = result.scalar_one()
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            await db.commit()

        client = device_manager.get_client(device_id)
        if not client:
            await self._fail_task(task_id, "No Moonraker client")
            return

        coord = await CoordinateMapper.load_calibration(
            async_session(), device_id
        ) if False else CoordinateMapper()  # Use default mapping if no calibration

        async with async_session() as db2:
            coord = await CoordinateMapper.load_calibration(db2, device_id)

        engine = FlowEngine(device_id, dev.ip, client, coord)
        self._running_engines[device_id] = engine

        final_status = TaskStatus.FAILED
        try:
            results = await engine.execute_yaml(yaml_content)
            async with async_session() as db:
                result = await db.execute(
                    select(TaskExecution).where(TaskExecution.id == task_id)
                )
                task = result.scalar_one()
                task.finished_at = datetime.now(timezone.utc)
                if results["stopped"]:
                    task.status = TaskStatus.STOPPED
                    final_status = TaskStatus.STOPPED
                elif results["failed"] > 0:
                    task.status = TaskStatus.FAILED
                    task.error = "; ".join(results["errors"])
                    final_status = TaskStatus.FAILED
                else:
                    task.status = TaskStatus.SUCCESS
                    final_status = TaskStatus.SUCCESS
                await db.commit()
        except Exception as e:
            await self._fail_task(task_id, str(e))

        await ws_manager.broadcast("task_complete", {
            "device_id": device_id, "task_id": task_id,
            "status": final_status.value,
        })

    async def _fail_task(self, task_id: int, error: str):
        async with async_session() as db:
            result = await db.execute(
                select(TaskExecution).where(TaskExecution.id == task_id)
            )
            task = result.scalar_one()
            task.status = TaskStatus.FAILED
            task.error = error
            task.finished_at = datetime.now(timezone.utc)
            await db.commit()

    def stop_device(self, device_id: int):
        engine = self._running_engines.get(device_id)
        if engine:
            engine.stop()

    async def dispatch_batch(self, device_ids: list[int], yaml_content: str) -> list[int]:
        task_ids = []
        for did in device_ids:
            try:
                tid = await self.dispatch_task(did, yaml_content)
                task_ids.append(tid)
            except ValueError as e:
                logger.warning("Skip device %d: %s", did, e)
        return task_ids


scheduler = Scheduler()
