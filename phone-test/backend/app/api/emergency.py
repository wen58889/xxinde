from fastapi import APIRouter, Depends

from app.auth import verify_token
from app.schemas import MessageOut
from app.services.device_manager import device_manager

router = APIRouter(prefix="/api/v1", tags=["emergency"])


@router.post("/emergency_stop", response_model=MessageOut)
async def emergency_stop(_=Depends(verify_token)):
    await device_manager.set_estop_all()
    return {"message": "Emergency stop triggered for all devices"}


@router.post("/emergency_reset", response_model=MessageOut)
async def emergency_reset(_=Depends(verify_token)):
    await device_manager.reset_all()
    return {"message": "All devices reset from ESTOP"}


@router.post("/devices/{device_id}/estop", response_model=MessageOut)
async def device_estop(device_id: int, _=Depends(verify_token)):
    await device_manager.set_estop(device_id)
    return {"message": f"Device {device_id} emergency stopped"}
