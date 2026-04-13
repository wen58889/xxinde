from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_token
from app.schemas import CalibrationRequest, CalibrationOut, OffsetRequest
from app.services.coordinate import CoordinateMapper
from app.models.calibration import CalibrationData

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
        db, device_id, req.pixel_points, req.mech_points,
        offset_x=req.offset_x, offset_y=req.offset_y,
    )
    return cal


@router.patch("/{device_id}/calibration/offset", response_model=CalibrationOut)
async def update_offset(
    device_id: int,
    req: OffsetRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(
        select(CalibrationData).where(CalibrationData.device_id == device_id)
    )
    cal = result.scalar_one_or_none()
    if not cal:
        raise HTTPException(404, "No calibration data for this device")
    cal.offset_x = req.offset_x
    cal.offset_y = req.offset_y
    await db.commit()
    await db.refresh(cal)
    return cal


@router.get("/{device_id}/calibration", response_model=Optional[CalibrationOut])
async def get_calibration(
    device_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    result = await db.execute(
        select(CalibrationData).where(CalibrationData.device_id == device_id)
    )
    return result.scalar_one_or_none()
