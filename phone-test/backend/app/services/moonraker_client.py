from __future__ import annotations

import logging
import asyncio
import time
import aiohttp

from app.config import get_settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_RETRIES = 3
READY_CACHE_TTL = 8.0

_op_session: aiohttp.ClientSession | None = None
_hb_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def _get_shared_session() -> aiohttp.ClientSession:
    global _op_session
    if _op_session is None or _op_session.closed:
        async with _session_lock:
            if _op_session is None or _op_session.closed:
                s = get_settings()
                connector = aiohttp.TCPConnector(
                    limit=s.connection_pool_limit,
                    limit_per_host=s.connection_pool_limit_per_host,
                    ttl_dns_cache=s.connection_pool_ttl_dns_cache,
                    keepalive_timeout=s.connection_pool_keepalive,
                    enable_cleanup_closed=True,
                )
                _op_session = aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                )
                logger.info(
                    "Operation session created: limit=%d, limit_per_host=%d, keepalive=%ds",
                    s.connection_pool_limit, s.connection_pool_limit_per_host, s.connection_pool_keepalive,
                )
    return _op_session


async def _get_heartbeat_session() -> aiohttp.ClientSession:
    global _hb_session
    if _hb_session is None or _hb_session.closed:
        async with _session_lock:
            if _hb_session is None or _hb_session.closed:
                s = get_settings()
                connector = aiohttp.TCPConnector(
                    limit=s.connection_pool_limit,
                    limit_per_host=s.connection_pool_limit_per_host,
                    ttl_dns_cache=s.connection_pool_ttl_dns_cache,
                    keepalive_timeout=s.connection_pool_keepalive,
                    enable_cleanup_closed=True,
                )
                _hb_session = aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                )
                logger.info(
                    "Heartbeat session created: limit=%d, limit_per_host=%d, keepalive=%ds",
                    s.connection_pool_limit, s.connection_pool_limit_per_host, s.connection_pool_keepalive,
                )
    return _hb_session


async def close_shared_session():
    global _op_session, _hb_session
    for name, sess in [("op", _op_session), ("hb", _hb_session)]:
        if sess and not sess.closed:
            await sess.close()
            logger.info("Closed %s session", name)
    _op_session = None
    _hb_session = None


class DeviceConnectionError(Exception):
    pass


class MoonrakerClient:
    def __init__(self, ip: str, port: int = 7125):
        self.ip = ip
        self.port = port
        self.base_url = f"http://{ip}:{port}"
        self._recovery_lock = asyncio.Lock()
        self._recovery_times: list[float] = []
        self._ready_cache_time: float = 0.0
        self._stats_fast: int = 0
        self._stats_slow: int = 0

    def invalidate_ready_cache(self) -> None:
        self._ready_cache_time = 0.0

    def _is_ready_cached(self) -> bool:
        return (time.monotonic() - self._ready_cache_time) < READY_CACHE_TTL

    def _mark_ready_cached(self) -> None:
        self._ready_cache_time = time.monotonic()

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
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * attempt)
                elif attempt == MAX_RETRIES:
                    raise DeviceConnectionError(
                        f"Moonraker {self.ip} unreachable after {MAX_RETRIES} retries"
                    ) from e

    async def send_gcode(self, gcode: str) -> dict:
        logger.info("[%s] G-code: %s", self.ip, gcode)
        timeout = TIMEOUT_SECONDS
        if gcode.strip().upper().startswith("G28"):
            timeout = 15.0
        session = await _get_shared_session()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.request(
                    "POST",
                    f"{self.base_url}/printer/gcode/script",
                    json={"script": gcode},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise DeviceConnectionError(
                            f"Moonraker {self.ip} returned {resp.status}: {text[:200]}"
                        )
                    return await resp.json()
            except (aiohttp.ClientError, TimeoutError, OSError) as e:
                logger.warning(
                    "Moonraker %s attempt %d/%d failed: %s", self.ip, attempt, MAX_RETRIES, e
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * attempt)
                elif attempt == MAX_RETRIES:
                    raise DeviceConnectionError(
                        f"Moonraker {self.ip} unreachable after {MAX_RETRIES} retries"
                    ) from e
        return {}

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
        s = get_settings()
        url = f"{self.base_url}/server/info"
        session = await _get_heartbeat_session()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=s.heartbeat_timeout),
            ) as resp:
                return resp.status < 500
        except (aiohttp.ClientError, TimeoutError, OSError):
            return False

    async def get_klippy_state(self) -> str:
        s = get_settings()
        url = f"{self.base_url}/server/info"
        session = await _get_heartbeat_session()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=s.heartbeat_timeout),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", {}).get("klippy_state", "unknown")
                return "error"
        except (aiohttp.ClientError, TimeoutError, OSError):
            return "unreachable"

    async def _wait_for_state(
        self, target: str, timeout: float, poll_interval: float = 2.0,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            state = await self.get_klippy_state()
            if state == target:
                return True
            if state == "shutdown":
                return False
        return False

    async def _try_server_restart(self) -> bool:
        s = get_settings()
        try:
            session = await _get_shared_session()
            async with session.post(
                f"{self.base_url}/server/restart",
                timeout=aiohttp.ClientTimeout(total=s.recovery_server_restart_timeout),
            ) as resp:
                logger.info("[%s] server/restart sent (status=%d)", self.ip, resp.status)
                return resp.status < 500
        except Exception as e:
            logger.warning("[%s] server/restart failed: %s", self.ip, e)
            return False

    async def _try_ssh_restart(self) -> bool:
        try:
            from app.services.ssh_tool import get_ssh_tool
            ssh = get_ssh_tool()
            return await ssh.restart_service(self.ip, "klipper")
        except Exception as e:
            logger.warning("[%s] SSH restart failed: %s", self.ip, e)
            return False

    async def _progressive_recover_from_shutdown(self) -> None:
        s = get_settings()
        start = time.monotonic()
        logger.info("[%s] Level1: FIRMWARE_RESTART", self.ip)
        try:
            session = await _get_shared_session()
            async with session.post(
                f"{self.base_url}/printer/firmware_restart",
                timeout=aiohttp.ClientTimeout(total=s.recovery_firmware_timeout),
            ) as resp:
                if resp.status < 500:
                    logger.info("[%s] Level1 succeeded (status=%d)", self.ip, resp.status)
                    await self._broadcast_recovery("Level1", True, start)
                    return
                raise Exception(f"status {resp.status}")
        except Exception as e:
            logger.warning("[%s] Level1 failed: %s, trying Level2", self.ip, e)
            await self._broadcast_recovery("Level1", False, start)

        start = time.monotonic()
        logger.info("[%s] Level2: server/restart", self.ip)
        if await self._try_server_restart():
            logger.info("[%s] Level2 succeeded", self.ip)
            await self._broadcast_recovery("Level2", True, start)
            return
        await self._broadcast_recovery("Level2", False, start)

        start = time.monotonic()
        logger.info("[%s] Level3: SSH restart klipper", self.ip)
        if await self._try_ssh_restart():
            logger.info("[%s] Level3 succeeded", self.ip)
            await self._broadcast_recovery("Level3", True, start)
            return
        await self._broadcast_recovery("Level3", False, start)

        raise DeviceConnectionError(f"Cannot recover MCU from shutdown on {self.ip} (all 3 levels failed)")

    async def _broadcast_recovery(self, level: str, success: bool, start: float) -> None:
        try:
            from app.ws_manager import ws_manager
            duration_ms = int((time.monotonic() - start) * 1000)
            await ws_manager.broadcast("mcu_recovery", {
                "ip": self.ip,
                "level": level,
                "success": success,
                "duration_ms": duration_ms,
            })
        except Exception:
            pass

    async def _broadcast_event(self, event: str, data: dict) -> None:
        try:
            from app.ws_manager import ws_manager
            await ws_manager.broadcast(event, data)
        except Exception:
            pass

    def _is_recovery_circuit_open(self) -> bool:
        s = get_settings()
        now = time.monotonic()
        cutoff = now - s.recovery_window
        self._recovery_times = [t for t in self._recovery_times if t > cutoff]
        return len(self._recovery_times) >= s.recovery_max_attempts

    def _record_recovery(self) -> None:
        self._recovery_times.append(time.monotonic())

    async def ensure_ready(self, max_wait: float | None = None) -> None:
        if self._is_ready_cached():
            self._stats_fast += 1
            return

        self._stats_slow += 1
        s = get_settings()
        if max_wait is None:
            max_wait = s.recovery_max_wait

        start = time.monotonic()

        async with self._recovery_lock:
            if self._is_ready_cached():
                return

            if self._is_recovery_circuit_open():
                await self._broadcast_event("mcu_recovery_circuit_open", {
                    "ip": self.ip,
                    "attempts": len(self._recovery_times),
                })
                raise DeviceConnectionError(
                    f"Recovery circuit open for {self.ip} "
                    f"({len(self._recovery_times)} attempts in {s.recovery_window}s window)"
                )

            state = await self.get_klippy_state()
            if state == "ready":
                self._mark_ready_cached()
                return

            logger.warning("[%s] MCU state=%s, auto-recovering...", self.ip, state)

            if state == "startup":
                ok = await self._wait_for_state(
                    "ready", timeout=s.recovery_startup_wait, poll_interval=2.0,
                )
                if ok:
                    logger.info("[%s] MCU startup → ready (waited)", self.ip)
                    self._mark_ready_cached()
                    return
                logger.warning("[%s] MCU startup did not resolve, trying server/restart", self.ip)
                if not await self._try_server_restart():
                    if not await self._try_ssh_restart():
                        raise DeviceConnectionError(
                            f"Cannot recover MCU from startup on {self.ip}"
                        )

            elif state == "shutdown":
                await self._progressive_recover_from_shutdown()

            elif state in ("disconnected", "error"):
                if not await self._try_server_restart():
                    if not await self._try_ssh_restart():
                        raise DeviceConnectionError(
                            f"Cannot recover MCU from {state} on {self.ip}"
                        )

            self._record_recovery()

            deadline = time.monotonic() + max_wait
            while time.monotonic() < deadline:
                await asyncio.sleep(3)
                state = await self.get_klippy_state()
                if state == "ready":
                    logger.info("[%s] MCU recovered to ready", self.ip)
                    self._mark_ready_cached()
                    return
                if state == "shutdown":
                    logger.warning("[%s] MCU shutdown again during recovery, retrying server/restart", self.ip)
                    await self._try_server_restart()
                logger.debug("[%s] MCU state=%s, waiting...", self.ip, state)

            await self._broadcast_event("mcu_recovery_timeout", {
                "ip": self.ip,
                "last_state": state,
            })
            raise DeviceConnectionError(
                f"MCU on {self.ip} did not reach 'ready' state within {max_wait}s (last: {state})"
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if elapsed_ms > 100:
            logger.warning("[%s] ensure_ready slow path took %dms", self.ip, elapsed_ms)

    def get_stats(self) -> dict:
        return {"fast": self._stats_fast, "slow": self._stats_slow}
