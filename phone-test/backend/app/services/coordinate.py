from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.calibration import CalibrationData

logger = logging.getLogger(__name__)

# Machine limits
MECH_X_MAX = 150.0
MECH_Y_MAX = 150.0


class CoordinateMapper:
    def __init__(self, calibration: CalibrationData | None = None):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._transform = None
        if calibration:
            self._load(calibration)

    def _load(self, cal: CalibrationData):
        self.offset_x = cal.offset_x
        self.offset_y = cal.offset_y
        px = cal.pixel_points   # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        mx = cal.mech_points
        if len(px) >= 2 and len(mx) >= 2:
            # Simple linear: use top-left and bottom-right
            self._px_tl = px[0]
            self._px_br = px[2] if len(px) > 2 else px[1]
            self._mx_tl = mx[0]
            self._mx_br = mx[2] if len(mx) > 2 else mx[1]

    def pixel_to_mech(self, px: float, py: float) -> tuple[float, float]:
        if self._transform is None and hasattr(self, "_px_tl"):
            # Linear interpolation
            px_w = self._px_br[0] - self._px_tl[0]
            px_h = self._px_br[1] - self._px_tl[1]
            mx_w = self._mx_br[0] - self._mx_tl[0]
            mx_h = self._mx_br[1] - self._mx_tl[1]

            if px_w == 0 or px_h == 0:
                raise ValueError("Invalid calibration: zero pixel span")

            mx = self._mx_tl[0] + (px - self._px_tl[0]) / px_w * mx_w + self.offset_x
            my = self._mx_tl[1] + (py - self._px_tl[1]) / px_h * mx_h + self.offset_y
        else:
            # Fallback: direct proportional mapping (1280x720 -> 150x150)
            mx = (px / 1280) * MECH_X_MAX + self.offset_x
            my = (py / 720) * MECH_Y_MAX + self.offset_y

        # Clamp
        mx = max(0.0, min(MECH_X_MAX, mx))
        my = max(0.0, min(MECH_Y_MAX, my))
        return (round(mx, 2), round(my, 2))

    def set_offset(self, dx: float, dy: float):
        self.offset_x = dx
        self.offset_y = dy

    @staticmethod
    async def save_calibration(
        db: AsyncSession,
        device_id: int,
        pixel_points: list,
        mech_points: list,
    ) -> CalibrationData:
        result = await db.execute(
            select(CalibrationData).where(CalibrationData.device_id == device_id)
        )
        cal = result.scalar_one_or_none()
        if cal:
            cal.pixel_points = pixel_points
            cal.mech_points = mech_points
        else:
            cal = CalibrationData(
                device_id=device_id,
                pixel_points=pixel_points,
                mech_points=mech_points,
            )
            db.add(cal)
        await db.commit()
        await db.refresh(cal)
        logger.info("Calibration saved for device %d", device_id)
        return cal

    @staticmethod
    async def load_calibration(db: AsyncSession, device_id: int) -> "CoordinateMapper":
        result = await db.execute(
            select(CalibrationData).where(CalibrationData.device_id == device_id)
        )
        cal = result.scalar_one_or_none()
        return CoordinateMapper(cal)
