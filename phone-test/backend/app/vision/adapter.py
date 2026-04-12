from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TextResult:
    text: str
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    confidence: float = 1.0


@dataclass
class MatchResult:
    """Template match result."""
    x: float          # center x
    y: float          # center y
    w: float          # matched width
    h: float          # matched height
    confidence: float  # TM_CCOEFF_NORMED score (0~1)
    template_name: str = ""


# Keep VisionTarget as backwards-compatible alias for frontend API
@dataclass
class VisionTarget:
    label: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "template"
    confidence: float = 0.0


class VisionAdapter(ABC):
    """Vision adapter interface — OpenCV template matching + OCR.

    No AI inference: deterministic, reproducible, industrial-grade.
    """

    @abstractmethod
    async def find_icon(
        self, screenshot: bytes, template_name: str, app_name: str = "",
        threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        """Find an icon by matching a template image.

        Returns center (x, y) in pixel space, or None if not found.
        """
        ...

    @abstractmethod
    async def find_element(
        self, screenshot: bytes, template_name: str, app_name: str = "",
        threshold: float = 0.85,
    ) -> tuple[float, float] | None:
        """Find a UI element by matching a template image.

        Returns center (x, y) in pixel space, or None if not found.
        """
        ...

    @abstractmethod
    async def detect_page_state(
        self,
        screenshot: bytes,
        templates: list[str] | None = None,
        ocr_keywords: list[str] | None = None,
        app_name: str = "",
        threshold: float = 0.80,
    ) -> bool:
        """Detect if the current page matches expected state.

        Uses template matching and/or OCR keyword verification.
        Returns True if at least one template matches OR all keywords found.
        """
        ...

    @abstractmethod
    async def verify_action(self, before: bytes, after: bytes) -> float:
        """Compare before/after screenshots using SSIM.

        Returns similarity score (0~1). Low score = screen changed = action worked.
        """
        ...

    @abstractmethod
    async def read_text(
        self, screenshot: bytes, region: tuple[int, int, int, int] | None = None,
    ) -> list[TextResult]:
        """OCR: extract all visible text with positions."""
        ...

    @abstractmethod
    async def detect_anomaly(
        self, screenshot: bytes, app_name: str = "",
    ) -> str | None:
        """Check for known error dialogs/popups by matching anomaly templates.

        Returns anomaly description string, or None if screen looks normal.
        """
        ...

    @abstractmethod
    async def detect_targets(
        self, screenshot: bytes, app_name: str = "",
        threshold: float = 0.85,
    ) -> list[VisionTarget]:
        """Match all templates in the app's icon directory.

        Returns list of matched targets with positions and confidence.
        """
        ...
