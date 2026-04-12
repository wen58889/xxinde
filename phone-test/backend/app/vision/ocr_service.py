"""PaddleOCR-based text recognition service.

Singleton: model loaded once, reused for all requests.
Optimized for Chinese mobile screen text recognition.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from io import BytesIO

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    np = None   # type: ignore
    _CV2_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TextResult:
    """Single OCR detection result."""
    text: str
    x: float       # center x
    y: float       # center y
    w: float       # bounding box width
    h: float       # bounding box height
    confidence: float


class OCRService:
    """Thread-safe PaddleOCR wrapper. Model loaded lazily on first call."""

    _instance: OCRService | None = None
    _lock = threading.Lock()

    def __new__(cls) -> OCRService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            import os
            os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    lang='ch',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
                self._initialized = True
                logger.info("PaddleOCR 3.x model loaded successfully (lang=ch, CPU)")
            except ImportError:
                logger.error("PaddleOCR not installed. Run: pip install paddlepaddle paddleocr")
                raise
            except Exception as e:
                logger.error("Failed to initialize PaddleOCR: %s", e)
                raise

    def read_text(
        self,
        screenshot: bytes,
        region: tuple[int, int, int, int] | None = None,
    ) -> list[TextResult]:
        """Run OCR on screenshot bytes.

        Args:
            screenshot: JPEG/PNG image bytes.
            region: Optional (x1, y1, x2, y2) to crop before OCR.

        Returns:
            List of TextResult with text, position, and confidence.
        """
        self._ensure_loaded()

        arr = np.frombuffer(screenshot, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning("OCR: failed to decode image")
            return []

        # Optional region crop
        if region:
            x1, y1, x2, y2 = region
            h, w = img.shape[:2]
            x1 = max(0, min(x1, w))
            y1 = max(0, min(y1, h))
            x2 = max(x1 + 1, min(x2, w))
            y2 = max(y1 + 1, min(y2, h))
            img = img[y1:y2, x1:x2]

        # Downscale large images to speed up OCR inference
        # PaddleOCR on CPU is slow for high-res images; 960px width is a good balance
        h, w = img.shape[:2]
        OCR_MAX_WIDTH = 960
        scale = 1.0
        if w > OCR_MAX_WIDTH:
            scale = OCR_MAX_WIDTH / w
            new_w = OCR_MAX_WIDTH
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.debug("OCR: downscaled %dx%d -> %dx%d (scale=%.2f)", w, h, new_w, new_h, scale)

        # Convert BGR to RGB for PaddleOCR
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        try:
            text_results: list[TextResult] = []
            for result in self._ocr.predict(img_rgb):
                rec_texts = result.get('rec_texts', [])
                rec_scores = result.get('rec_scores', [])
                rec_polys = result.get('rec_polys', [])
                for i, text in enumerate(rec_texts):
                    if not text or not text.strip():
                        continue
                    conf = rec_scores[i] if i < len(rec_scores) else 0.0

                    # Compute bounding box from 4-point polygon
                    if i < len(rec_polys):
                        pts = np.array(rec_polys[i], dtype=np.float32)
                        bx1 = float(pts[:, 0].min())
                        by1 = float(pts[:, 1].min())
                        bx2 = float(pts[:, 0].max())
                        by2 = float(pts[:, 1].max())
                    else:
                        bx1 = by1 = bx2 = by2 = 0.0

                    cx = (bx1 + bx2) / 2.0
                    cy = (by1 + by2) / 2.0
                    bw = bx2 - bx1
                    bh = by2 - by1

                    # Map coordinates back to original image size if downscaled
                    if scale < 1.0:
                        inv = 1.0 / scale
                        cx *= inv
                        cy *= inv
                        bw *= inv
                        bh *= inv

                    # Offset back if region was cropped
                    if region:
                        cx += region[0]
                        cy += region[1]

                    text_results.append(TextResult(
                        text=text.strip(),
                        x=cx,
                        y=cy,
                        w=bw,
                        h=bh,
                        confidence=float(conf),
                    ))
                break  # predict() yields per-image; we only have one
        except Exception as e:
            logger.error("PaddleOCR inference failed: %s", e, exc_info=True)
            raise

        return text_results

    def find_text(
        self,
        screenshot: bytes,
        keyword: str,
        region: tuple[int, int, int, int] | None = None,
    ) -> tuple[float, float] | None:
        """Find the center position of a specific text keyword.

        Returns (center_x, center_y) or None if not found.
        """
        texts = self.read_text(screenshot, region)
        keyword_lower = keyword.lower()
        for t in texts:
            if keyword_lower in t.text.lower():
                return (t.x, t.y)
        return None

    def is_loaded(self) -> bool:
        return self._initialized


# Module-level singleton
ocr_service = OCRService()
