"""SSH remote diagnostic and repair tool for N1 devices.

Uses asyncssh for all remote operations. Commands are restricted to a whitelist
for security. Connections are reused per device IP.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

import asyncssh

from app.config import get_settings

logger = logging.getLogger(__name__)


class SSHConnectionError(Exception):
    pass


class SSHAuthError(Exception):
    pass


class SSHCommandNotAllowedError(Exception):
    pass


ALLOWED_COMMANDS: list[re.Pattern] = [
    re.compile(r"tail\s+-\d+\s+\S*klippy\.log"),
    re.compile(r"tail\s+-\d+\s+\S*moonraker\.log"),
    re.compile(r"systemctl\s+(restart|status)\s+(klipper|moonraker|klipper-moonraker)"),
    re.compile(r"ls\s+/dev/serial/by-id/?"),
    re.compile(r"ls\s+-la\s+/dev/serial/by-id/?"),
    re.compile(r"pgrep\s+-x\s+\S+"),
    re.compile(r"ps\s+aux\s*\|\s*grep\s+\S+"),
    re.compile(r"df\s+-h"),
    re.compile(r"free\s+-m"),
    re.compile(r"uptime"),
    re.compile(r"mkdir\s+-p\s+\S+"),
    re.compile(r"rm\s+-f\s+\S+"),
    re.compile(r"pgrep\s+-x\s+pulseaudio"),
    re.compile(r"pulseaudio\s+\S+.*"),
    re.compile(r"pactl\s+\S+.*"),
    re.compile(r"bluetoothctl\s+info\s+\S+"),
    re.compile(r"mpg123\s+\S+.*"),
    re.compile(r"paplay\s+\S+.*"),
    re.compile(r"ffplay\s+\S+.*"),
    re.compile(r"aplay\s+\S+.*"),
    re.compile(r"\(\s*echo\s+power\s+on.*\)\s*\|\s*bluetoothctl.*"),
]


@dataclass
class SSHResult:
    command: str
    exit_status: int
    stdout: str
    stderr: str
    duration_ms: int
    error: str | None = None


@dataclass
class DiagnosisReport:
    device_ip: str
    klippy_state: str = "unknown"
    klippy_log: str = ""
    moonraker_log: str = ""
    mcu_serial_devices: list[str] = field(default_factory=list)
    klippy_process_running: bool = False
    moonraker_process_running: bool = False
    errors: list[str] = field(default_factory=list)


class SSHTool:
    def __init__(self):
        self._connections: dict[str, asyncssh.SSHClientConnection] = {}
        self._max_stdout_len = 10000
        self._max_stderr_len = 5000

    async def _get_connection(self, device_ip: str) -> asyncssh.SSHClientConnection:
        conn = self._connections.get(device_ip)
        if conn and not conn.is_closed():
            return conn
        s = get_settings()
        try:
            conn = await asyncssh.connect(
                device_ip,
                username=s.n1_ssh_user,
                password=s.n1_ssh_password,
                known_hosts=None,
                connect_timeout=s.ssh_connect_timeout,
            )
            self._connections[device_ip] = conn
            logger.debug("SSH connection established to %s", device_ip)
            return conn
        except asyncssh.PermissionDenied as e:
            raise SSHAuthError(f"SSH auth failed for {device_ip}: {e}") from e
        except (asyncssh.DisconnectError, asyncssh.ConnectionLost, OSError, TimeoutError) as e:
            self._connections.pop(device_ip, None)
            raise SSHConnectionError(f"SSH connect failed to {device_ip}: {e}") from e

    def _validate_command(self, command: str) -> None:
        for pattern in ALLOWED_COMMANDS:
            if pattern.fullmatch(command.strip()):
                return
        raise SSHCommandNotAllowedError(f"Command not in whitelist: {command}")

    async def run_command(
        self, device_ip: str, command: str, timeout: float | None = None,
    ) -> SSHResult:
        self._validate_command(command)
        s = get_settings()
        timeout = timeout or s.ssh_command_timeout
        start = time.monotonic()
        last_err: str | None = None

        for attempt in range(1, s.ssh_max_retries + 1):
            try:
                conn = await self._get_connection(device_ip)
                result = await conn.run(command, check=False, timeout=timeout)
                elapsed = int((time.monotonic() - start) * 1000)
                stdout = (result.stdout or "")[: self._max_stdout_len]
                stderr = (result.stderr or "")[: self._max_stderr_len]
                return SSHResult(
                    command=command,
                    exit_status=result.exit_status,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=elapsed,
                )
            except SSHAuthError:
                raise
            except SSHConnectionError as e:
                last_err = str(e)
                logger.warning(
                    "SSH command attempt %d/%d failed for %s: %s",
                    attempt, s.ssh_max_retries, device_ip, e,
                )
            except (asyncssh.DisconnectError, asyncssh.ConnectionLost) as e:
                self._connections.pop(device_ip, None)
                last_err = str(e)
                logger.warning(
                    "SSH connection lost to %s attempt %d: %s", device_ip, attempt, e,
                )
            except (OSError, TimeoutError) as e:
                self._connections.pop(device_ip, None)
                last_err = str(e)
                logger.warning(
                    "SSH error to %s attempt %d: %s", device_ip, attempt, e,
                )

        elapsed = int((time.monotonic() - start) * 1000)
        return SSHResult(
            command=command, exit_status=-1, stdout="", stderr="",
            duration_ms=elapsed, error=last_err,
        )

    async def read_logs(
        self, device_ip: str, klippy_lines: int = 100, moonraker_lines: int = 50,
    ) -> tuple[str, str]:
        kr = await self.run_command(device_ip, f"tail -{klippy_lines} ~/klippy.log")
        mr = await self.run_command(device_ip, f"tail -{moonraker_lines} ~/moonraker.log")
        return (kr.stdout or kr.error or "", mr.stdout or mr.error or "")

    async def restart_service(self, device_ip: str, service: str) -> bool:
        if service not in ("klipper", "moonraker", "klipper-moonraker"):
            raise ValueError(f"Invalid service: {service}")
        result = await self.run_command(
            device_ip, f"systemctl restart {service}", timeout=15.0,
        )
        if result.exit_status == 0:
            await asyncio.sleep(5)
            logger.info("Service %s restarted on %s via SSH", service, device_ip)
            return True
        logger.warning(
            "Failed to restart %s on %s: exit=%d stderr=%s",
            service, device_ip, result.exit_status, (result.stderr or "")[:200],
        )
        return False

    async def check_mcu_connection(self, device_ip: str) -> list[str]:
        result = await self.run_command(device_ip, "ls /dev/serial/by-id/")
        if result.exit_status == 0 and result.stdout.strip():
            return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return []

    async def check_processes(self, device_ip: str) -> dict[str, bool]:
        kr = await self.run_command(device_ip, "pgrep -x klippy")
        mr = await self.run_command(device_ip, "pgrep -x moonraker")
        return {"klippy": kr.exit_status == 0, "moonraker": mr.exit_status == 0}

    async def diagnose(self, device_ip: str) -> DiagnosisReport:
        report = DiagnosisReport(device_ip=device_ip)

        try:
            klippy_log, moonraker_log = await self.read_logs(device_ip)
            report.klippy_log = klippy_log
            report.moonraker_log = moonraker_log
        except Exception as e:
            report.errors.append(f"read_logs failed: {e}")

        try:
            report.mcu_serial_devices = await self.check_mcu_connection(device_ip)
        except Exception as e:
            report.errors.append(f"check_mcu failed: {e}")

        try:
            procs = await self.check_processes(device_ip)
            report.klippy_process_running = procs["klippy"]
            report.moonraker_process_running = procs["moonraker"]
        except Exception as e:
            report.errors.append(f"check_processes failed: {e}")

        if "shutdown" in report.klippy_log[-500:]:
            report.klippy_state = "shutdown"
        elif report.klippy_process_running:
            report.klippy_state = "running"
        else:
            report.klippy_state = "not_running"

        return report

    async def preflight_check(self, device_ip: str) -> tuple[bool, str]:
        try:
            procs = await self.check_processes(device_ip)
        except Exception as e:
            return (False, f"SSH process check failed: {e}")

        if not procs.get("klippy"):
            return (False, "Klippy process not running")

        try:
            devices = await self.check_mcu_connection(device_ip)
        except Exception as e:
            return (False, f"MCU check failed: {e}")

        if not devices:
            return (False, "No MCU serial device found")

        return (True, "OK")

    async def close_all(self) -> None:
        for ip, conn in list(self._connections.items()):
            if not conn.is_closed():
                try:
                    conn.close()
                    await conn.wait_closed()
                except Exception:
                    pass
        count = len(self._connections)
        self._connections.clear()
        if count:
            logger.info("Closed %d SSH connections", count)


_ssh_tool: SSHTool | None = None


def get_ssh_tool() -> SSHTool:
    global _ssh_tool
    if _ssh_tool is None:
        _ssh_tool = SSHTool()
    return _ssh_tool
