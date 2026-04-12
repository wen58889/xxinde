"""Template icon management API — CRUD for template matching images.

Templates stored at: templates/icons/{app_name}/{icon_name}.jpg
Common templates at: templates/icons/_common/
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import verify_token
from app.config import get_settings
from app.services.screenshot import capture_screenshot, ScreenshotError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.device import Device

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/templates/icons", tags=["template-icons"])


def _get_matcher():
    from app.vision.opencv_matcher import OpenCVMatcher
    return OpenCVMatcher()


def _icons_dir() -> str:
    return getattr(get_settings(), 'template_icons_dir', 'templates/icons')


@router.get("")
async def list_icons(_=Depends(verify_token)) -> dict[str, Any]:
    """List all app folders and their template icons."""
    base = _icons_dir()
    if not os.path.isdir(base):
        return {"apps": {}}

    apps: dict[str, list[dict]] = {}
    for app_name in sorted(os.listdir(base)):
        app_dir = os.path.join(base, app_name)
        if not os.path.isdir(app_dir):
            continue
        icons = []
        for fname in sorted(os.listdir(app_dir)):
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext not in ('jpg', 'jpeg', 'png'):
                continue
            fpath = os.path.join(app_dir, fname)
            icons.append({
                "app": app_name,
                "name": fname,
                "size": os.path.getsize(fpath),
                "path": f"{app_name}/{fname}",
            })
        apps[app_name] = icons

    return {"apps": apps}


@router.get("/{app_name}/{icon_name}")
async def get_icon(app_name: str, icon_name: str, _=Depends(verify_token)):
    """Return the template image file."""
    base = _icons_dir()
    fpath = os.path.join(base, app_name, icon_name)
    if not os.path.isfile(fpath):
        raise HTTPException(404, f"Template not found: {app_name}/{icon_name}")

    # Security: prevent path traversal
    real = os.path.realpath(fpath)
    base_real = os.path.realpath(base)
    if not real.startswith(base_real):
        raise HTTPException(403, "Path traversal blocked")

    return FileResponse(fpath, media_type="image/jpeg")


@router.post("/{app_name}/{icon_name}")
async def upload_icon(
    app_name: str,
    icon_name: str,
    file: UploadFile = File(...),
    _=Depends(verify_token),
):
    """Upload a template image file."""
    base = _icons_dir()
    app_dir = os.path.join(base, app_name)

    # Security: prevent path traversal
    real_app_dir = os.path.realpath(app_dir)
    real_base = os.path.realpath(base)
    if not real_app_dir.startswith(real_base):
        raise HTTPException(403, "Path traversal blocked")

    os.makedirs(app_dir, exist_ok=True)

    # Ensure icon_name has valid extension
    if not icon_name.lower().endswith(('.jpg', '.jpeg', '.png')):
        icon_name = icon_name + '.jpg'

    fpath = os.path.join(app_dir, icon_name)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(413, "File too large (max 5MB)")

    with open(fpath, 'wb') as f:
        f.write(data)

    size_kb = round(len(data) / 1024, 2)
    logger.info("Template uploaded: %s/%s (%.1f KB)", app_name, icon_name, size_kb)
    return {"message": "ok", "path": f"{app_name}/{icon_name}", "size_kb": size_kb}


class CropRequest(BaseModel):
    device_id: int
    x: int
    y: int
    w: int
    h: int
    app_name: str
    icon_name: str


@router.post("/crop")
async def crop_from_screenshot(
    req: CropRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Capture screenshot from device and crop a region as template."""
    result = await db.execute(select(Device).where(Device.id == req.device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    try:
        screenshot = await capture_screenshot(dev.ip)
    except ScreenshotError as e:
        raise HTTPException(502, str(e))

    base = _icons_dir()
    icon_name = req.icon_name
    if not icon_name.lower().endswith(('.jpg', '.jpeg', '.png')):
        icon_name = icon_name + '.jpg'

    save_path = os.path.join(base, req.app_name, icon_name)

    # Security: prevent path traversal
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    real_save = os.path.realpath(os.path.dirname(save_path))
    real_base = os.path.realpath(base)
    if not real_save.startswith(real_base):
        raise HTTPException(403, "Path traversal blocked")

    try:
        _get_matcher().crop_and_save(screenshot, req.x, req.y, req.w, req.h, save_path)
    except ValueError as e:
        logger.error("Crop failed for %s/%s: %s", req.app_name, icon_name, e)
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Crop unexpected error: %s", e, exc_info=True)
        raise HTTPException(500, f"Crop failed: {e}")

    size_kb = round(os.path.getsize(save_path) / 1024, 2)
    logger.info("Template cropped: %s/%s from device %d", req.app_name, icon_name, req.device_id)
    return {"message": "ok", "path": f"{req.app_name}/{icon_name}", "size_kb": size_kb}


class CropBase64Request(BaseModel):
    image_base64: str
    x: int
    y: int
    w: int
    h: int
    app_name: str
    icon_name: str


@router.post("/crop_base64")
async def crop_from_base64(
    req: CropBase64Request,
    _=Depends(verify_token),
):
    """Crop a region from a base64 image and save as template."""
    try:
        screenshot = base64.b64decode(req.image_base64)
    except Exception:
        raise HTTPException(400, "Invalid base64 image")

    base = _icons_dir()
    icon_name = req.icon_name
    if not icon_name.lower().endswith(('.jpg', '.jpeg', '.png')):
        icon_name = icon_name + '.jpg'

    save_path = os.path.join(base, req.app_name, icon_name)

    real_save = os.path.realpath(os.path.dirname(save_path))
    real_base = os.path.realpath(base)
    if not real_save.startswith(real_base):
        raise HTTPException(403, "Path traversal blocked")

    try:
        _get_matcher().crop_and_save(screenshot, req.x, req.y, req.w, req.h, save_path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    size_kb = round(os.path.getsize(save_path) / 1024, 2)
    return {"message": "ok", "path": f"{req.app_name}/{icon_name}", "size_kb": size_kb}


@router.delete("/{app_name}/{icon_name}")
async def delete_icon(app_name: str, icon_name: str, _=Depends(verify_token)):
    """Delete a template image."""
    base = _icons_dir()
    fpath = os.path.join(base, app_name, icon_name)

    real = os.path.realpath(fpath)
    real_base = os.path.realpath(base)
    if not real.startswith(real_base):
        raise HTTPException(403, "Path traversal blocked")

    if not os.path.isfile(fpath):
        raise HTTPException(404, f"Template not found: {app_name}/{icon_name}")

    os.remove(fpath)
    logger.info("Template deleted: %s/%s", app_name, icon_name)
    return {"message": "ok"}


@router.post("/folder/{app_name}")
async def create_folder(app_name: str, _=Depends(verify_token)):
    """Create a new app template folder."""
    base = _icons_dir()
    app_dir = os.path.join(base, app_name)

    real_app_dir = os.path.realpath(app_dir)
    real_base = os.path.realpath(base)
    if not real_app_dir.startswith(real_base):
        raise HTTPException(403, "Path traversal blocked")

    os.makedirs(app_dir, exist_ok=True)
    return {"message": "ok", "folder": app_name}
