import re
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import verify_token
from app.config import get_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"


class VisionSettingsBody(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    vllm_base_url: str = ""
    modelscope_token: str = ""
    custom_api_base_url: str = ""
    custom_api_key: str = ""
    custom_api_model: str = ""


def _update_env_file(updates: dict[str, str]) -> None:
    lines: list[str] = _ENV_PATH.read_text(encoding="utf-8").splitlines() if _ENV_PATH.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in updates:
            key = m.group(1)
            written.add(key)
            new_lines.append(f"{key}={updates[key]}")
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in written:
            new_lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@router.post("/vision")
async def save_vision_settings(body: VisionSettingsBody, _=Depends(verify_token)):
    updates: dict[str, str] = {
        "CUSTOM_API_BASE_URL": body.custom_api_base_url.strip(),
        "CUSTOM_API_KEY": body.custom_api_key.strip(),
        "CUSTOM_API_MODEL": body.custom_api_model.strip(),
    }
    if body.openai_api_key:
        updates["OPENAI_API_KEY"] = body.openai_api_key
    if body.anthropic_api_key:
        updates["ANTHROPIC_API_KEY"] = body.anthropic_api_key
    if body.vllm_base_url:
        updates["VLLM_BASE_URL"] = body.vllm_base_url
    if body.modelscope_token:
        updates["MODELSCOPE_TOKEN"] = body.modelscope_token

    _update_env_file(updates)
    get_settings.cache_clear()
    # Reinit vision_manager so new API keys take effect immediately (no restart needed)
    from app.vision.manager import vision_manager
    vision_manager.reinit()
    return {"status": "ok"}


@router.get("/vision")
async def get_vision_settings(_=Depends(verify_token)):
    s = get_settings()
    return {
        "vllm_base_url": s.vllm_base_url,
        "custom_api_base_url": s.custom_api_base_url,
        "custom_api_model": s.custom_api_model,
        "screen_crop": s.screen_crop,
        # Never return keys to frontend; just signal whether they are set
        "openai_configured": bool(s.openai_api_key),
        "anthropic_configured": bool(s.anthropic_api_key),
        "custom_configured": bool(s.custom_api_key and s.custom_api_base_url),
        "modelscope_configured": bool(s.modelscope_token),
    }


class ScreenCropBody(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


@router.post("/screen_crop")
async def save_screen_crop(body: ScreenCropBody, _=Depends(verify_token)):
    """Save the phone screen crop region derived from calibration corner clicks."""
    crop_str = f"{body.x1},{body.y1},{body.x2},{body.y2}"
    _update_env_file({"SCREEN_CROP": crop_str})
    get_settings.cache_clear()
    return {"status": "ok", "screen_crop": crop_str}
