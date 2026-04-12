from __future__ import annotations

import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_RETRIES = 3
HEARTBEAT_TIMEOUT = 2  # 心跳只用2s超时，不重试

# 全局共享的 TCPConnector + ClientSession，避免每次请求都创建新连接
_shared_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_shared_session() -> aiohttp.ClientSession:
    """获取或创建全局共享的 aiohttp session（带连接池限制）"""
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        async with _session_lock:
            if _shared_session is None or _shared_session.closed:
                connector = aiohttp.TCPConnector(
                    limit=30,           # 最大30并发连接
                    limit_per_host=2,   # 每台设备最多2并发
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                _shared_session = aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                )
    return _shared_session


async def close_shared_session():
    """应用关闭时调用，释放共享session"""
    global _shared_session
    if _shared_session and not _shared_session.closed:
        await _shared_session.close()
        _shared_session = None


class DeviceConnectionError(Exception):
    pass


class MoonrakerClient:
    def __init__(self, ip: str, port: int = 7125):
        self.ip = ip
        self.port = port
        self.base_url = f"http://{ip}:{port}"

    async def _request(self, method: str, path: str, json_data: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        session = await _get_shared_session()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.request(
                    method, url, json=json_data,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise DeviceConnectionError(
                            f"Moonraker {self.ip} returned {resp.status}: {text}"
                        )
                    return await resp.json()
            except (aiohttp.ClientError, TimeoutError, OSError) as e:
                logger.warning(
                    "Moonraker %s attempt %d/%d failed: %s", self.ip, attempt, MAX_RETRIES, e
                )
                if attempt == MAX_RETRIES:
                    raise DeviceConnectionError(
                        f"Moonraker {self.ip} unreachable after {MAX_RETRIES} retries"
                    ) from e

    async def send_gcode(self, gcode: str) -> dict:
        logger.info("[%s] G-code: %s", self.ip, gcode)
        return await self._request("POST", "/printer/gcode/script", {"script": gcode})

    async def get_printer_status(self) -> dict:
        return await self._request(
            "GET",
            "/printer/objects/query?print_stats&toolhead&gcode_move",
        )

    async def home(self) -> dict:
        return await self.send_gcode("G28")

    async def emergency_stop(self) -> dict:
        logger.warning("[%s] EMERGENCY STOP", self.ip)
        return await self._request("POST", "/printer/emergency_stop")

    async def firmware_restart(self) -> dict:
        logger.warning("[%s] Firmware restart", self.ip)
        return await self._request("POST", "/printer/firmware_restart")

    async def is_alive(self) -> bool:
        """快速心跳探测：1次尝试，2s超时，不重试"""
        url = f"{self.base_url}/server/info"
        session = await _get_shared_session()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=HEARTBEAT_TIMEOUT),
            ) as resp:
                return resp.status < 500
        except (aiohttp.ClientError, TimeoutError, OSError):
            return False
