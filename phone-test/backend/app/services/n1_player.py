"""Play TTS audio on N1 device via SSH — scp the audio file then play with auto-detected player."""
from __future__ import annotations

import asyncio
import logging
import os

import asyncssh

from app.config import get_settings

logger = logging.getLogger(__name__)

N1_AUDIO_DIR = "/tmp/phone_tts"

PLAYER_COMMANDS = {
    "mpg123": "mpg123 -q '{path}'",
    "ffplay": "ffplay -nodisp -autoexit -loglevel quiet '{path}'",
    "aplay": "aplay -q '{path}'",
}


async def _detect_player(conn) -> str:
    for player in ("mpg123", "ffplay", "aplay"):
        r = await conn.run(f"which {player}", check=False)
        if r.exit_status == 0:
            return player
    return ""


async def play_on_device(device_ip: str, local_audio_path: str) -> None:
    s = get_settings()
    remote_path = f"{N1_AUDIO_DIR}/{os.path.basename(local_audio_path)}"
    is_mp3 = local_audio_path.endswith(".mp3")

    try:
        async with asyncssh.connect(
            device_ip,
            username=s.n1_ssh_user,
            password=s.n1_ssh_password,
            known_hosts=None,
            connect_timeout=5,
        ) as conn:
            await conn.run(f"mkdir -p {N1_AUDIO_DIR}", check=True)
            await asyncssh.scp(local_audio_path, (conn, remote_path))

            configured_player = (s.n1_audio_player or "").strip()
            if configured_player and configured_player in PLAYER_COMMANDS:
                player = configured_player
            else:
                player = await _detect_player(conn)

            if not player:
                logger.warning("N1 %s: no audio player found (mpg123/ffplay/aplay)", device_ip)
                await conn.run(f"rm -f '{remote_path}'", check=False)
                return

            if is_mp3 and player == "aplay":
                player = await _detect_player(conn) or "aplay"
                if player == "aplay":
                    wav_path = remote_path.replace(".mp3", ".wav")
                    r = await conn.run(f"ffmpeg -y -i '{remote_path}' -f wav '{wav_path}'", check=False, timeout=10)
                    if r.exit_status == 0:
                        await conn.run(f"rm -f '{remote_path}'", check=False)
                        remote_path = wav_path
                    else:
                        player = ""

            if player:
                cmd = PLAYER_COMMANDS.get(player, f"{player} '{remote_path}'")
                cmd = cmd.format(path=remote_path)
                result = await conn.run(cmd, check=False, timeout=30)
                if result.exit_status != 0:
                    stderr = result.stderr.strip() if result.stderr else ""
                    logger.warning("N1 player %s exit=%d stderr=%s", player, result.exit_status, stderr[:200])
                else:
                    logger.info("N1 audio played on %s via %s", device_ip, player)

            await conn.run(f"rm -f '{remote_path}'", check=False)
    except (asyncssh.DisconnectError, asyncssh.ConnectionLost) as e:
        logger.warning("N1 SSH connection issue to %s: %s", device_ip, e)
    except (OSError, TimeoutError) as e:
        logger.warning("N1 SSH connect failed to %s: %s", device_ip, e)
    except Exception as e:
        logger.error("N1 play_on_device error (%s): %s", device_ip, e)
