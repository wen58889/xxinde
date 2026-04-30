from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_token
from app.config import get_settings
from app.services.tts_service import synthesize_and_play

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice_type: int = 0  # 0 = use default from config


@router.post("/synthesize")
async def tts_synthesize(req: TTSRequest, _=Depends(verify_token)):
    """Text-to-speech synthesis via Tencent Cloud TTS API.
    Returns audio URL that can be played on the N1 device via Bluetooth speaker."""
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    settings = get_settings()
    voice_type = req.voice_type if req.voice_type > 0 else settings.tts_voice_type

    try:
        result = await synthesize_and_play(req.text, voice_type)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"TTS synthesis failed: {e}")


@router.get("/status")
async def tts_status(_=Depends(verify_token)):
    """Check if TTS is configured."""
    s = get_settings()
    return {"configured": bool(s.tts_secret_id and s.tts_secret_key)}
