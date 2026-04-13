from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.calibration import CalibrationData
from app.config import get_settings

logger = logging.getLogger(__name__)

# Machine limits
MECH_X_MAX = 150.0
MECH_Y_MAX = 150.0


class CoordinateMapper:
    def __init__(self, calibration: CalibrationData | None = None):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._transform = None
        self._calibrated = False
        if calibration:
            self._load(calibration)

    def _load(self, cal: CalibrationData):
        self.offset_x = cal.offset_x
        self.offset_y = cal.offset_y
        px = cal.pixel_points   # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        mx = cal.mech_points
        # Points layout: 0=TL, 1=TR, 2=BL, 3=BR
        # We need at least 2 points for any mapping.
        # With 4 points, use bilinear interpolation (handles axis inversion).
        if len(px) >= 4 and len(mx) >= 4:
            self._px = px  # [TL, TR, BL, BR]
            self._mx = mx
            self._calibrated = True
            self._bilinear = True
        elif len(px) >= 2 and len(mx) >= 2:
            # Fallback: diagonal linear (2-3 points)
            self._px_tl = px[0]
            self._px_br = px[-1]
            self._mx_tl = mx[0]
            self._mx_br = mx[-1]
            self._calibrated = True
            self._bilinear = False

    def pixel_to_mech(self, px: float, py: float) -> tuple[float, float]:
        if self._calibrated and getattr(self, "_bilinear", False):
            # 4-point bilinear interpolation
            # Handles axis inversion (e.g. pixel X and mech X in opposite directions)
            #
            # Layout: 0=TL, 1=TR, 2=BL, 3=BR
            #   px[0]=(x_tl,y_tl)  px[1]=(x_tr,y_tr)
            #   px[2]=(x_bl,y_bl)  px[3]=(x_br,y_br)
            #
            # Normalize pixel coords to [0,1] range using TL-BR diagonal,
            # then bilinear blend the 4 mech corners.
            px_tl, px_tr, px_bl, px_br = self._px
            mx_tl, mx_tr, mx_bl, mx_br = self._mx

            # Use TL→BR diagonal for normalization
            diag_px_x = px_br[0] - px_tl[0]
            diag_px_y = px_br[1] - px_tl[1]
            if diag_px_x == 0 or diag_px_y == 0:
                raise ValueError("Invalid calibration: zero pixel span")

            # Normalized coords: u in X direction, v in Y direction
            u = (px - px_tl[0]) / diag_px_x
            v = (py - px_tl[1]) / diag_px_y

            # Bilinear interpolation of mech coordinates
            # At (u,v): blend = (1-u)(1-v)*TL + u*(1-v)*TR + (1-u)*v*BL + u*v*BR
            w00 = (1 - u) * (1 - v)  # TL weight
            w10 = u * (1 - v)         # TR weight
            w01 = (1 - u) * v         # BL weight
            w11 = u * v               # BR weight

            mx = w00 * mx_tl[0] + w10 * mx_tr[0] + w01 * mx_bl[0] + w11 * mx_br[0] + self.offset_x
            my = w00 * mx_tl[1] + w10 * mx_tr[1] + w01 * mx_bl[1] + w11 * mx_br[1] + self.offset_y
        elif self._calibrated and hasattr(self, "_px_tl"):
            # 2-3 point diagonal linear interpolation
            px_w = self._px_br[0] - self._px_tl[0]
            px_h = self._px_br[1] - self._px_tl[1]
            mx_w = self._mx_br[0] - self._mx_tl[0]
            mx_h = self._mx_br[1] - self._mx_tl[1]

            if px_w == 0 or px_h == 0:
                raise ValueError("Invalid calibration: zero pixel span")

            mx = self._mx_tl[0] + (px - self._px_tl[0]) / px_w * mx_w + self.offset_x
            my = self._mx_tl[1] + (py - self._px_tl[1]) / px_h * mx_h + self.offset_y
        else:
            # Fallback: use screen_crop region for proportional mapping
            # This is more accurate than raw 1280x720 -> 150x150 because
            # it accounts for the phone screen's position within the camera image.
            settings = get_settings()
            crop = settings.screen_crop
            if crop:
                parts = crop.split(",")
                if len(parts) == 4:
                    cx1, cy1, cx2, cy2 = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                    # Map pixel within crop region to [0, MECH_MAX]
                    # Pixels outside crop are extrapolated
                    crop_w = cx2 - cx1
                    crop_h = cy2 - cy1
                    if crop_w > 0 and crop_h > 0:
                        mx = ((px - cx1) / crop_w) * MECH_X_MAX + self.offset_x
                        my = ((py - cy1) / crop_h) * MECH_Y_MAX + self.offset_y
                    else:
                        mx = (px / 1280) * MECH_X_MAX + self.offset_x
                        my = (py / 720) * MECH_Y_MAX + self.offset_y
                else:
                    mx = (px / 1280) * MECH_X_MAX + self.offset_x
                    my = (py / 720) * MECH_Y_MAX + self.offset_y
            else:
                # No crop info: raw proportional mapping
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
