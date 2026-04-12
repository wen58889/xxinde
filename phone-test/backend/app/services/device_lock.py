from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class DeviceLockManager:
    def __init__(self):
        self._locks: dict[int, asyncio.Lock] = {}
        self._owners: dict[int, int | None] = {}

    def _get_lock(self, device_id: int) -> asyncio.Lock:
        if device_id not in self._locks:
            self._locks[device_id] = asyncio.Lock()
            self._owners[device_id] = None
        return self._locks[device_id]

    async def acquire(self, device_id: int, task_id: int, timeout: float = 30.0) -> bool:
        lock = self._get_lock(device_id)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            self._owners[device_id] = task_id
            logger.info("Device %d locked by task %d", device_id, task_id)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "Device %d lock timeout, owned by task %s",
                device_id, self._owners.get(device_id),
            )
            return False

    def release(self, device_id: int, task_id: int):
        lock = self._get_lock(device_id)
        if self._owners.get(device_id) == task_id:
            self._owners[device_id] = None
            if lock.locked():
                lock.release()
            logger.info("Device %d released by task %d", device_id, task_id)
        else:
            logger.warning(
                "Device %d release rejected: owner=%s, requester=%d",
                device_id, self._owners.get(device_id), task_id,
            )

    def is_locked(self, device_id: int) -> bool:
        lock = self._get_lock(device_id)
        return lock.locked()

    def get_owner(self, device_id: int) -> int | None:
        return self._owners.get(device_id)


device_lock_manager = DeviceLockManager()
