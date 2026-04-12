"""Vision test endpoints — OpenCV template matching + PaddleOCR health & testing."""
from __future__ import annotations

import base64
import time
import logging
import os
from typing import Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.auth import verify_token
from app.config import get_settings
from app.database import get_db
from app.models.device import Device
from app.services.screenshot import capture_screenshot, ScreenshotError
from app.vision.manager import vision_manager
from app.vision.ocr_service import ocr_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/vision", tags=["vision"])


@router.get("/health")
async def vision_health(_=Depends(verify_token)) -> Dict[str, Any]:
    """Check OpenCV and PaddleOCR readiness."""
    results: Dict[str, Any] = {}

    # OpenCV check
    try:
        import cv2
        results["opencv"] = {
            "status": "ok",
            "version": cv2.__version__,
        }
    except ImportError:
        results["opencv"] = {"status": "error", "error": "opencv-python-headless not installed"}

    # PaddleOCR check
    try:
        ocr_service._ensure_loaded()
        results["paddleocr"] = {"status": "ok"}
    except Exception as e:
        results["paddleocr"] = {"status": "error", "error": str(e)}

    # Template icons directory
    settings = get_settings()
    icons_dir = getattr(settings, 'template_icons_dir', 'templates/icons')
    if os.path.isdir(icons_dir):
        app_count = sum(
            1 for d in os.listdir(icons_dir)
            if os.path.isdir(os.path.join(icons_dir, d))
        )
        template_count = sum(
            len([f for f in os.listdir(os.path.join(icons_dir, d))
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
            for d in os.listdir(icons_dir)
            if os.path.isdir(os.path.join(icons_dir, d))
        )
        results["templates"] = {
            "status": "ok",
            "icons_dir": icons_dir,
            "app_folders": app_count,
            "total_templates": template_count,
        }
    else:
        results["templates"] = {
            "status": "warning",
            "icons_dir": icons_dir,
            "error": "目录不存在，请创建模板文件夹",
        }

    # Flat fields for frontend convenience
    results["opencv_version"] = results.get("opencv", {}).get("version", "N/A")
    results["ocr_loaded"] = results.get("paddleocr", {}).get("status") == "ok"
    results["template_dir"] = results.get("templates", {}).get("icons_dir", "N/A")
    results["total_templates"] = results.get("templates", {}).get("total_templates", 0)

    return results


class MatchTestRequest(BaseModel):
    device_id: Optional[int] = None
    image_base64: Optional[str] = None  # alternative: provide image directly
    app_name: str = ""
    template_name: str = ""            # specific template, or empty for all
    threshold: float = 0.85


@router.post("/match_test")
async def match_test(
    req: MatchTestRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
) -> Dict[str, Any]:
    """Run template matching test. Returns matched locations + confidence."""
    t0 = time.monotonic()

    # Get screenshot
    screenshot: bytes | None = None
    if req.image_base64:
        try:
            screenshot = base64.b64decode(req.image_base64)
        except Exception:
            raise HTTPException(400, "Invalid base64 image")
    elif req.device_id is not None:
        result = await db.execute(select(Device).where(Device.id == req.device_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(404, "Device not found")
        try:
            screenshot = await capture_screenshot(dev.ip)
        except ScreenshotError as e:
            raise HTTPException(502, f"Screenshot failed: {e}")
    else:
        raise HTTPException(400, "Provide device_id or image_base64")

    # Run matching
    try:
        if req.template_name:
            # Match specific template — returns full MatchResult with x/y/w/h/confidence
            from app.vision.adapter import VisionTarget
            raw = await vision_manager.match_template_detail(
                screenshot, req.template_name, req.app_name, req.threshold,
            )
            matches = [
                VisionTarget(
                    label=req.template_name,
                    x=m.x, y=m.y, w=m.w, h=m.h,
                    kind="template", confidence=m.confidence,
                )
                for m in raw
            ]
        else:
            # Match all templates in app folder
            matches = await vision_manager.detect_targets(
                screenshot, req.app_name, req.threshold,
            )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("Match test failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Match test failed: {type(e).__name__}: {e}")

    latency_ms = round((time.monotonic() - t0) * 1000)
    return {
        "status": "ok",
        "count": len(matches),
        "latency_ms": latency_ms,
        "threshold": req.threshold,
        "result": [
            {
                "label": t.label,
                "x": round(t.x, 1),
                "y": round(t.y, 1),
                "w": round(t.w, 1),
                "h": round(t.h, 1),
                "confidence": round(t.confidence, 4),
            }
            for t in matches
        ],
    }


class OCRTestRequest(BaseModel):
    device_id: Optional[int] = None
    image_base64: Optional[str] = None


@router.post("/ocr_test")
async def ocr_test(
    req: OCRTestRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
) -> Dict[str, Any]:
    """Run OCR text recognition test."""
    t0 = time.monotonic()

    screenshot: bytes | None = None
    if req.image_base64:
        try:
            screenshot = base64.b64decode(req.image_base64)
        except Exception:
            raise HTTPException(400, "Invalid base64 image")
    elif req.device_id is not None:
        result = await db.execute(select(Device).where(Device.id == req.device_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(404, "Device not found")
        try:
            screenshot = await capture_screenshot(dev.ip)
        except ScreenshotError as e:
            raise HTTPException(502, f"Screenshot failed: {e}")
    else:
        raise HTTPException(400, "Provide device_id or image_base64")

    try:
        texts = await vision_manager.read_text(screenshot)
    except Exception as e:
        logger.error("OCR test failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR inference failed: {e}")
    latency_ms = round((time.monotonic() - t0) * 1000)

    return {
        "status": "ok",
        "count": len(texts),
        "latency_ms": latency_ms,
        "result": [
            {
                "text": t.text,
                "x": round(t.x, 1),
                "y": round(t.y, 1),
                "w": round(t.w, 1),
                "h": round(t.h, 1),
                "confidence": round(t.confidence, 4),
            }
            for t in texts
        ],
    }
