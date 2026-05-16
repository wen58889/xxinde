"""Play TTS audio on N1 device via SSH — uses ssh_tool for connection reuse."""
from __future__ import annotations

import asyncio
import logging
import os

from app.services.ssh_tool import get_ssh_tool, SSHConnectionError, SSHAuthError
from app.config import get_settings

logger = logging.getLogger(__name__)

N1_AUDIO_DIR = "/tmp/phone_tts"


async def _ensure_pulse(conn) -> bool:
    r = await conn.run("pgrep -x pulseaudio", check=False)
    if r.exit_status == 0:
        return True
    r2 = await conn.run("pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null", check=False, timeout=5)
    await asyncio.sleep(0.5)
    r3 = await conn.run("pgrep -x pulseaudio", check=False)
    return r3.exit_status == 0


async def _connect_bt_if_needed(conn, mac: str) -> None:
    r = await conn.run(f"bluetoothctl info {mac} 2>&1 | grep 'Connected: yes'", check=False, timeout=5)
    if r.exit_status == 0 and "Connected: yes" in (r.stdout or ""):
        return
    script = f"""(
echo power on
echo connect {mac}
sleep 6
echo quit
) | bluetoothctl 2>&1"""
    await conn.run(script, check=False, timeout=15)
    await asyncio.sleep(1)


async def play_on_device(device_ip: str, local_audio_path: str) -> None:
    s = get_settings()
    ssh = get_ssh_tool()
    remote_path = f"{N1_AUDIO_DIR}/{os.path.basename(local_audio_path)}"
    is_mp3 = local_audio_path.endswith(".mp3")

    try:
        conn = await ssh._get_connection(device_ip)

        await conn.run(f"mkdir -p {N1_AUDIO_DIR}", check=True)

        import asyncssh
        await asyncssh.scp(local_audio_path, (conn, remote_path), timeout=10)

        pulse_ok = await _ensure_pulse(conn)

        if pulse_ok:
            r = await conn.run("pactl list sinks short 2>/dev/null | grep bluez", check=False, timeout=3)
            if r.exit_status == 0 and r.stdout and r.stdout.strip():
                sink_line = r.stdout.strip().split("\n")[0]
                sink_name = sink_line.split("\t")[1] if "\t" in sink_line else ""
                if sink_name:
                    await conn.run(f"pactl set-default-sink {sink_name}", check=False, timeout=3)
                    await conn.run("pactl set-sink-volume @DEFAULT_SINK@ 75%", check=False, timeout=3)

            if is_mp3:
                cmd = f"mpg123 -o pulse -q '{remote_path}'"
            else:
                cmd = f"paplay '{remote_path}'"
        else:
            if is_mp3:
                cmd = f"ffplay -nodisp -autoexit -loglevel quiet '{remote_path}'"
            else:
                cmd = f"aplay -q '{remote_path}'"

        result = await conn.run(cmd, check=False, timeout=30)
        if result.exit_status != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            logger.warning("N1 player exit=%d stderr=%s", result.exit_status, stderr[:200])
            if pulse_ok and is_mp3:
                fallback = f"ffplay -nodisp -autoexit -loglevel quiet '{remote_path}'"
                r2 = await conn.run(fallback, check=False, timeout=30)
                if r2.exit_status == 0:
                    logger.info("N1 audio played on %s via ffplay (fallback)", device_ip)
                else:
                    logger.warning("N1 fallback ffplay also failed")
        else:
            logger.info("N1 audio played on %s", device_ip)

        await conn.run(f"rm -f '{remote_path}'", check=False)
    except SSHAuthError as e:
        logger.error("N1 SSH auth failed to %s: %s", device_ip, e)
    except SSHConnectionError as e:
        logger.warning("N1 SSH connection issue to %s: %s", device_ip, e)
    except Exception as e:
        logger.error("N1 play_on_device error (%s): %s", device_ip, e)
