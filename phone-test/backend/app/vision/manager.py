from __future__ import annotations

import logging
from app.vision.adapter import TextResult, VisionTarget
from app.config import get_settings

logger = logging.getLogger(__name__)

_CV2_AVAILABLE = False
try:
    from app.vision.template_match_adapter import TemplateMatchAdapter
    _CV2_AVAILABLE = True
except ImportError:
    TemplateMatchAdapter = None  # type: ignore
    logger.warning("OpenCV not installed — vision features disabled")


class VisionManager:
    """Manages vision: OpenCV template matching (primary) + OCR.

    Industrial-grade: deterministic, no AI inference in the main path.
    """

    def __init__(self):
        settings = get_settings()
        icons_dir = getattr(settings, 'template_icons_dir', 'templates/icons')
        if _CV2_AVAILABLE and TemplateMatchAdapter is not None:
            self._adapter = TemplateMatchAdapter(icons_dir=icons_dir)
            logger.info("VisionManager initialized: OpenCV + PaddleOCR (icons_dir=%s)", icons_dir)
        else:
            self._adapter = None
            logger.warning("VisionManager: no adapter available (cv2 not installed)")

    def reinit(self) -> None:
        """Rebuild adapter from current settings."""
        settings = get_settings()
        icons_dir = getattr(settings, 'template_icons_dir', 'templates/icons')
        if _CV2_AVAILABLE and TemplateMatchAdapter is not None:
            self._adapter = TemplateMatchAdapter(icons_dir=icons_dir)
            logger.info("VisionManager reinit: icons_dir=%s", icons_dir)
        else:
            logger.warning("VisionManager reinit skipped: cv2 not available")

    def _check_adapter(self):
        if self._adapter is None:
            raise RuntimeError("Vision not available: opencv-python-headless not installed")

    async def find_icon(
        self, screenshot: bytes, template_name: str,
        app_name: str = "", threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        self._check_adapter()
        return await self._adapter.find_icon(screenshot, template_name, app_name, threshold)

    async def match_template_detail(
        self, screenshot: bytes, template_name: str,
        app_name: str = "", threshold: float = 0.85,
    ) -> list:
        """Match a specific template, returning full MatchResult list."""
        self._check_adapter()
        return await self._adapter.match_template_detail(screenshot, template_name, app_name, threshold)

    async def find_element(
        self, screenshot: bytes, template_name: str,
        app_name: str = "", threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        self._check_adapter()
        return await self._adapter.find_element(screenshot, template_name, app_name, threshold)

    async def detect_page_state(
        self,
        screenshot: bytes,
        templates: list[str] | None = None,
        ocr_keywords: list[str] | None = None,
        app_name: str = "",
        threshold: float = 0.80,
    ) -> bool:
        self._check_adapter()
        return await self._adapter.detect_page_state(
            screenshot, templates, ocr_keywords, app_name, threshold,
        )

    async def verify_action(self, before: bytes, after: bytes) -> float:
        self._check_adapter()
        return await self._adapter.verify_action(before, after)

    async def read_text(
        self, screenshot: bytes, region: tuple[int, int, int, int] | None = None,
    ) -> list[TextResult]:
        self._check_adapter()
        return await self._adapter.read_text(screenshot, region)

    async def detect_anomaly(
        self, screenshot: bytes, app_name: str = "",
    ) -> str | None:
        self._check_adapter()
        return await self._adapter.detect_anomaly(screenshot, app_name)

    async def detect_targets(
        self, screenshot: bytes, app_name: str = "",
        threshold: float = 0.85,
    ) -> list[VisionTarget]:
        self._check_adapter()
        return await self._adapter.detect_targets(screenshot, app_name, threshold)


vision_manager = VisionManager()
