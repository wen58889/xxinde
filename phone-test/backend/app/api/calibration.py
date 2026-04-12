from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_token
from app.schemas import CalibrationRequest, CalibrationOut
from app.services.coordinate import CoordinateMapper

router = APIRouter(prefix="/api/v1/devices", tags=["calibration"])


@router.post("/{device_id}/calibrate", response_model=CalibrationOut)
async def calibrate_device(
    device_id: int,
    req: CalibrationRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    if len(req.pixel_points) < 2 or len(req.mech_points) < 2:
        raise HTTPException(400, "Need at least 2 calibration points")

    cal = await CoordinateMapper.save_calibration(
        db, device_id, req.pixel_points, req.mech_points
    )
    return cal


@router.get("/{device_id}/calibration", response_model=Optional[CalibrationOut])
async def get_calibration(
    device_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    from sqlalchemy import select
    from app.models.calibration import CalibrationData
    result = await db.execute(
        select(CalibrationData).where(CalibrationData.device_id == device_id)
    )
    return result.scalar_one_or_none()
