import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import verify_token
from app.config import get_settings
from app.database import async_session
from app.models.device import Device
from app.services.tts_service import synthesize_and_play
from app.services.n1_player import play_on_device

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice_type: int = 0
    device_id: int = 0


@router.post("/synthesize")
async def tts_synthesize(req: TTSRequest, _=Depends(verify_token)):
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    settings = get_settings()
    voice_type = req.voice_type if req.voice_type > 0 else settings.tts_voice_type

    try:
        result = await synthesize_and_play(req.text, voice_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"TTS synthesis failed: {e}")

    if req.device_id > 0:
        device_ip = await _get_device_ip(req.device_id)
        if device_ip:
            local_path = str(Path("static/tts") / result["audio_url"].split("/")[-1])
            asyncio.create_task(_play_and_log(device_ip, local_path))
            result["played_on"] = device_ip

    return result


async def _get_device_ip(device_id: int) -> str | None:
    try:
        async with async_session() as db:
            r = await db.execute(select(Device.ip).where(Device.id == device_id))
            return r.scalar_one_or_none()
    except Exception as e:
        logger.error("Failed to get device IP: %s", e)
        return None


async def _play_and_log(device_ip: str, local_path: str):
    try:
        await play_on_device(device_ip, local_path)
    except Exception as e:
        logger.error("Background N1 play error: %s", e)


@router.get("/status")
async def tts_status(_=Depends(verify_token)):
    s = get_settings()
    return {"configured": True, "engine": s.tts_engine}
