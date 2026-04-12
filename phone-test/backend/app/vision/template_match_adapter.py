"""TemplateMatchAdapter — VisionAdapter implementation using OpenCV + PaddleOCR.

Industrial-grade: deterministic template matching, no AI inference.
Templates stored at: templates/icons/{app_name}/{icon_name}.jpg
Common templates at: templates/icons/_common/
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import partial

from app.vision.adapter import VisionAdapter, TextResult, VisionTarget
from app.vision.opencv_matcher import OpenCVMatcher
from app.vision.ocr_service import OCRService

logger = logging.getLogger(__name__)


class TemplateMatchAdapter(VisionAdapter):
    """OpenCV TM_CCOEFF_NORMED + PaddleOCR adapter.

    Thread-safe: all OpenCV/OCR calls run in executor to avoid blocking asyncio.
    """

    def __init__(self, icons_dir: str = "templates/icons"):
        self._matcher = OpenCVMatcher()
        self._ocr = OCRService()
        self._icons_dir = icons_dir

    def _template_path(self, template_name: str, app_name: str = "") -> str | None:
        """Resolve template file path. Search order:
        1. templates/icons/{app_name}/{template_name}.jpg
        2. templates/icons/{app_name}/{template_name}.png
        3. templates/icons/_common/{template_name}.jpg
        4. templates/icons/_common/{template_name}.png
        """
        candidates = []
        if app_name:
            app_dir = os.path.join(self._icons_dir, app_name)
            candidates.append(os.path.join(app_dir, f"{template_name}.jpg"))
            candidates.append(os.path.join(app_dir, f"{template_name}.png"))
        common_dir = os.path.join(self._icons_dir, "_common")
        candidates.append(os.path.join(common_dir, f"{template_name}.jpg"))
        candidates.append(os.path.join(common_dir, f"{template_name}.png"))

        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def _app_template_dir(self, app_name: str) -> str:
        """Return the directory for a specific app's templates."""
        if app_name:
            return os.path.join(self._icons_dir, app_name)
        return os.path.join(self._icons_dir, "_common")

    async def find_icon(
        self, screenshot: bytes, template_name: str, app_name: str = "",
        threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        path = self._template_path(template_name, app_name)
        if not path:
            logger.warning("Template not found: %s (app=%s)", template_name, app_name)
            return None

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(self._matcher.match_best, screenshot, path, threshold),
        )
        if result:
            logger.info(
                "find_icon hit: %s @ (%.0f, %.0f) conf=%.3f",
                template_name, result.x, result.y, result.confidence,
            )
            return (result.x, result.y)
        return None

    async def match_template_detail(
        self, screenshot: bytes, template_name: str, app_name: str = "",
        threshold: float = 0.85,
    ) -> list:
        """Match a specific template, returning full MatchResult list with x/y/w/h/confidence."""
        path = self._template_path(template_name, app_name)
        if not path:
            logger.warning("Template not found: %s (app=%s)", template_name, app_name)
            return []

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            partial(self._matcher.match_template, screenshot, path, threshold),
        )
        return results

    async def find_element(
        self, screenshot: bytes, template_name: str, app_name: str = "",
        threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        return await self.find_icon(screenshot, template_name, app_name, threshold)

    async def detect_page_state(
        self,
        screenshot: bytes,
        templates: list[str] | None = None,
        ocr_keywords: list[str] | None = None,
        app_name: str = "",
        threshold: float = 0.80,
    ) -> bool:
        # Strategy 1: check if any expected template exists on screen
        if templates:
            for tpl_name in templates:
                coords = await self.find_icon(screenshot, tpl_name, app_name, threshold)
                if coords:
                    logger.info("detect_page_state: template '%s' found", tpl_name)
                    return True

        # Strategy 2: check if all OCR keywords are present
        if ocr_keywords:
            loop = asyncio.get_event_loop()
            texts = await loop.run_in_executor(
                None,
                partial(self._ocr.read_text, screenshot),
            )
            all_text = " ".join(t.text for t in texts).lower()
            found_all = all(kw.lower() in all_text for kw in ocr_keywords)
            if found_all:
                logger.info("detect_page_state: all OCR keywords found: %s", ocr_keywords)
                return True
            # Log which keywords were missing
            missing = [kw for kw in ocr_keywords if kw.lower() not in all_text]
            logger.info("detect_page_state: missing keywords: %s", missing)

        # If neither strategy provided or both failed
        if not templates and not ocr_keywords:
            logger.warning("detect_page_state: no templates or keywords provided")
        return False

    async def verify_action(self, before: bytes, after: bytes) -> float:
        loop = asyncio.get_event_loop()
        ssim_score = await loop.run_in_executor(
            None,
            partial(OpenCVMatcher.compute_ssim, before, after),
        )
        logger.info("verify_action: SSIM=%.4f (low=changed, high=same)", ssim_score)
        return ssim_score

    async def read_text(
        self, screenshot: bytes, region: tuple[int, int, int, int] | None = None,
    ) -> list[TextResult]:
        loop = asyncio.get_event_loop()
        ocr_results = await loop.run_in_executor(
            None,
            partial(self._ocr.read_text, screenshot, region),
        )
        # Convert OCRService.TextResult → adapter.TextResult
        return [
            TextResult(
                text=r.text,
                x=r.x,
                y=r.y,
                w=r.w,
                h=r.h,
                confidence=r.confidence,
            )
            for r in ocr_results
        ]

    async def detect_anomaly(
        self, screenshot: bytes, app_name: str = "",
    ) -> str | None:
        # Match against known error/dialog templates in _common
        anomaly_dir = os.path.join(self._icons_dir, "_common")
        if not os.path.isdir(anomaly_dir):
            return None

        loop = asyncio.get_event_loop()

        # Look for templates starting with "error_" or "crash_" or "dialog_"
        for fname in os.listdir(anomaly_dir):
            name_lower = fname.lower()
            if not any(name_lower.startswith(p) for p in ("error_", "crash_", "dialog_", "popup_")):
                continue
            ext = fname.rsplit('.', 1)[-1] if '.' in fname else ''
            if ext not in ('jpg', 'jpeg', 'png'):
                continue

            fpath = os.path.join(anomaly_dir, fname)
            result = await loop.run_in_executor(
                None,
                partial(self._matcher.match_best, screenshot, fpath, 0.80),
            )
            if result:
                anomaly_name = fname.rsplit('.', 1)[0]
                logger.warning("Anomaly detected: %s (conf=%.3f)", anomaly_name, result.confidence)
                return f"检测到异常: {anomaly_name} (置信度 {result.confidence:.0%})"

        return None

    async def detect_targets(
        self, screenshot: bytes, app_name: str = "",
        threshold: float = 0.85,
    ) -> list[VisionTarget]:
        loop = asyncio.get_event_loop()
        targets: list[VisionTarget] = []

        # Match app-specific templates
        if app_name:
            app_dir = self._app_template_dir(app_name)
            if os.path.isdir(app_dir):
                matches = await loop.run_in_executor(
                    None,
                    partial(self._matcher.match_all_templates, screenshot, app_dir, threshold),
                )
                for m in matches:
                    targets.append(VisionTarget(
                        label=m.template_name,
                        x=m.x, y=m.y, w=m.w, h=m.h,
                        kind="template",
                        confidence=m.confidence,
                    ))

        # Also match common templates
        common_dir = os.path.join(self._icons_dir, "_common")
        if os.path.isdir(common_dir):
            matches = await loop.run_in_executor(
                None,
                partial(self._matcher.match_all_templates, screenshot, common_dir, threshold),
            )
            for m in matches:
                # Skip anomaly templates in target detection
                if any(m.template_name.startswith(p) for p in ("error_", "crash_", "dialog_", "popup_")):
                    continue
                targets.append(VisionTarget(
                    label=m.template_name,
                    x=m.x, y=m.y, w=m.w, h=m.h,
                    kind="template",
                    confidence=m.confidence,
                ))

        logger.info("detect_targets: %d matches (app=%s, threshold=%.2f)", len(targets), app_name, threshold)
        return targets
