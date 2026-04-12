"""OpenCV TM_CCOEFF_NORMED template matching engine.

Industrial-grade, deterministic image matching — no AI inference, 100% reproducible.
Supports multi-scale matching and NMS deduplication.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

try:
    import cv2
    import numpy as np
    from PIL import Image
    _CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    np = None   # type: ignore
    Image = None  # type: ignore
    _CV2_AVAILABLE = False

logger = logging.getLogger(__name__)

# Multi-scale factors: handles slight size differences across phone models
_SCALES = [0.8, 0.9, 1.0, 1.1, 1.2]

# NMS overlap threshold (IoU)
_NMS_IOU_THRESHOLD = 0.4


@dataclass
class MatchResult:
    """Single template match result."""
    x: float          # center x in screenshot pixel space
    y: float          # center y in screenshot pixel space
    w: float          # matched width
    h: float          # matched height
    confidence: float  # TM_CCOEFF_NORMED score (0~1)
    template_name: str = ""


def _bytes_to_cv(data: bytes) -> np.ndarray:
    """Convert raw image bytes (JPEG/PNG) to OpenCV BGR ndarray."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image bytes")
    return img


def _load_template_cv(path: str) -> np.ndarray:
    """Load template image file as OpenCV BGR ndarray.
    
    Uses numpy + cv2.imdecode instead of cv2.imread to support
    non-ASCII (Chinese) file paths on Windows.
    """
    # cv2.imread fails with non-ASCII paths on Windows;
    # read as bytes then decode instead
    with open(path, 'rb') as f:
        buf = np.frombuffer(f.read(), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Template not found or unreadable: {path}")
    return img


def _nms(results: list[MatchResult], iou_threshold: float = _NMS_IOU_THRESHOLD) -> list[MatchResult]:
    """Non-Maximum Suppression to remove overlapping detections."""
    if not results:
        return []
    # Sort by confidence descending
    results = sorted(results, key=lambda r: r.confidence, reverse=True)
    keep: list[MatchResult] = []
    for r in results:
        overlap = False
        for k in keep:
            # IoU calculation using center + size
            r_x1, r_y1 = r.x - r.w / 2, r.y - r.h / 2
            r_x2, r_y2 = r.x + r.w / 2, r.y + r.h / 2
            k_x1, k_y1 = k.x - k.w / 2, k.y - k.h / 2
            k_x2, k_y2 = k.x + k.w / 2, k.y + k.h / 2

            inter_x1 = max(r_x1, k_x1)
            inter_y1 = max(r_y1, k_y1)
            inter_x2 = min(r_x2, k_x2)
            inter_y2 = min(r_y2, k_y2)

            inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
            r_area = r.w * r.h
            k_area = k.w * k.h
            union_area = r_area + k_area - inter_area

            if union_area > 0 and inter_area / union_area > iou_threshold:
                overlap = True
                break
        if not overlap:
            keep.append(r)
    return keep


class OpenCVMatcher:
    """Deterministic template matching using cv2.TM_CCOEFF_NORMED.

    Thread-safe, stateless — all state lives in the template files on disk.
    """

    def match_template(
        self,
        screenshot: bytes,
        template_path: str,
        threshold: float = 0.85,
    ) -> list[MatchResult]:
        """Match a single template against a screenshot.

        Args:
            screenshot: JPEG/PNG bytes of the full screenshot.
            template_path: Absolute or relative path to the template image file.
            threshold: Minimum TM_CCOEFF_NORMED score to accept (0~1).

        Returns:
            List of MatchResult sorted by confidence descending.
        """
        screen = _bytes_to_cv(screenshot)
        template = _load_template_cv(template_path)
        template_name = Path(template_path).stem

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        th, tw = tpl_gray.shape[:2]
        sh, sw = screen_gray.shape[:2]

        all_matches: list[MatchResult] = []

        for scale in _SCALES:
            new_w = int(tw * scale)
            new_h = int(th * scale)

            # Skip if scaled template is larger than screenshot
            if new_w >= sw or new_h >= sh:
                continue
            # Skip if scaled template is too small
            if new_w < 8 or new_h < 8:
                continue

            scaled_tpl = cv2.resize(tpl_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(screen_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)

            # Find all locations above threshold
            locations = np.where(result >= threshold)
            for pt_y, pt_x in zip(*locations):
                score = float(result[pt_y, pt_x])
                center_x = pt_x + new_w / 2.0
                center_y = pt_y + new_h / 2.0
                all_matches.append(MatchResult(
                    x=center_x,
                    y=center_y,
                    w=float(new_w),
                    h=float(new_h),
                    confidence=score,
                    template_name=template_name,
                ))

        # NMS to remove overlapping detections across scales
        return _nms(all_matches)

    def match_best(
        self,
        screenshot: bytes,
        template_path: str,
        threshold: float = 0.85,
    ) -> MatchResult | None:
        """Return the single best match, or None if below threshold."""
        matches = self.match_template(screenshot, template_path, threshold)
        return matches[0] if matches else None

    def match_all_templates(
        self,
        screenshot: bytes,
        template_dir: str,
        threshold: float = 0.85,
    ) -> list[MatchResult]:
        """Match all template images in a directory against the screenshot.

        Scans for .jpg, .jpeg, .png files.
        Returns all matches above threshold, NMS-deduplicated.
        """
        if not os.path.isdir(template_dir):
            logger.warning("Template directory not found: %s", template_dir)
            return []

        all_matches: list[MatchResult] = []
        for fname in sorted(os.listdir(template_dir)):
            ext = fname.lower().rsplit('.', 1)[-1] if '.' in fname else ''
            if ext not in ('jpg', 'jpeg', 'png'):
                continue
            fpath = os.path.join(template_dir, fname)
            try:
                matches = self.match_template(screenshot, fpath, threshold)
                all_matches.extend(matches)
            except Exception as e:
                logger.warning("Failed to match template %s: %s", fname, e)

        return _nms(all_matches)

    @staticmethod
    def crop_and_save(
        screenshot: bytes,
        x: int,
        y: int,
        w: int,
        h: int,
        save_path: str,
    ) -> str:
        """Crop a region from the screenshot and save as template.

        Args:
            screenshot: JPEG/PNG bytes.
            x, y: Top-left corner of the crop region.
            w, h: Width and height of the crop.
            save_path: Where to save the cropped template image.

        Returns:
            The save_path on success.
        """
        screen = _bytes_to_cv(screenshot)
        sh, sw = screen.shape[:2]

        # Clamp to image bounds
        x1 = max(0, min(x, sw - 1))
        y1 = max(0, min(y, sh - 1))
        x2 = max(1, min(x + w, sw))
        y2 = max(1, min(y + h, sh))

        if x2 - x1 < 4 or y2 - y1 < 4:
            raise ValueError(f"Crop region too small: ({x1},{y1})-({x2},{y2})")

        cropped = screen[y1:y2, x1:x2]

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cv2.imwrite(save_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        logger.info("Template saved: %s (%dx%d)", save_path, x2 - x1, y2 - y1)
        return save_path

    @staticmethod
    def compute_ssim(image_a: bytes, image_b: bytes) -> float:
        """Compute structural similarity (SSIM) between two images.

        Returns a value in [0, 1] where 1 = identical.
        Used for verify_action (before/after comparison).
        """
        from skimage.metrics import structural_similarity as ssim

        a = _bytes_to_cv(image_a)
        b = _bytes_to_cv(image_b)

        # Resize b to match a if different sizes
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]))

        a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        b_gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

        score = ssim(a_gray, b_gray)
        return float(score)
