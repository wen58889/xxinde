from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_token
from app.models.task import TaskExecution
from app.schemas import ExecuteRequest, NaturalTaskRequest, RunYamlRequest, BatchRunRequest, TaskOut, MessageOut
from app.services.scheduler import scheduler
from app.services.device_manager import device_manager
from app.nlp.intent import parse_natural_instruction

router = APIRouter(prefix="/api/v1", tags=["tasks"])


@router.post("/devices/{device_id}/execute", response_model=TaskOut)
async def execute_on_device(
    device_id: int,
    req: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    # Build a simple YAML from the action
    yaml_content = f"steps:\n  - action: {req.action}\n"
    for k, v in req.params.items():
        yaml_content += f"    {k}: {v}\n"

    try:
        task_id = await scheduler.dispatch_task(device_id, yaml_content)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await db.execute(select(TaskExecution).where(TaskExecution.id == task_id))
    return result.scalar_one()


@router.post("/tasks/natural", response_model=MessageOut)
async def natural_task(req: NaturalTaskRequest, _=Depends(verify_token)):
    yaml_content = await parse_natural_instruction(req.instruction)

    if yaml_content == "__EMERGENCY_STOP__":
        await device_manager.set_estop_all()
        return {"message": "Emergency stop triggered for all devices"}

    if req.device_id:
        try:
            task_id = await scheduler.dispatch_task(req.device_id, yaml_content)
            return {"message": f"Task {task_id} dispatched to device {req.device_id}"}
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        return {"message": "Generated YAML (no device specified):\n" + yaml_content}


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(TaskExecution).where(TaskExecution.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.post("/devices/{device_id}/stop", response_model=MessageOut)
async def stop_device_task(device_id: int, _=Depends(verify_token)):
    scheduler.stop_device(device_id)
    return {"message": f"Stop signal sent to device {device_id}"}


@router.post("/devices/{device_id}/run_yaml", response_model=TaskOut)
async def run_yaml_on_device(
    device_id: int,
    req: RunYamlRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    try:
        task_id = await scheduler.dispatch_task(device_id, req.yaml_content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = await db.execute(select(TaskExecution).where(TaskExecution.id == task_id))
    return result.scalar_one()


@router.post("/tasks/batch_run", response_model=MessageOut)
async def batch_run_yaml(
    req: BatchRunRequest,
    _=Depends(verify_token),
):
    task_ids = await scheduler.dispatch_batch(req.device_ids, req.yaml_content)
    return {"message": f"Dispatched {len(task_ids)} tasks to {len(req.device_ids)} devices"}
