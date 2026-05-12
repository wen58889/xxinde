"""AI Agent API — start/stop autonomous agent loop on a device."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import verify_token
from app.database import async_session
from app.models.device import Device
from app.services.device_manager import device_manager
from app.services.agent_engine import AgentEngine
from app.services.coordinate import CoordinateMapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

_active_agents: dict[int, AgentEngine] = {}


class AgentStartRequest(BaseModel):
    task: str
    max_steps: int = 30


@router.post("/devices/{device_id}/start")
async def start_agent(device_id: int, req: AgentStartRequest, _=Depends(verify_token)):
    if device_id in _active_agents:
        raise HTTPException(409, "Agent already running on this device")

    client = device_manager.get_client(device_id)
    if not client:
        raise HTTPException(404, "Device not found")

    async with async_session() as db:
        r = await db.execute(select(Device.ip).where(Device.id == device_id))
        device_ip = r.scalar_one_or_none()
        if not device_ip:
            raise HTTPException(404, "Device IP not found")
        coord_mapper = await CoordinateMapper.load_calibration(db, device_id)
    engine = AgentEngine(device_id, device_ip, client, coord_mapper)
    _active_agents[device_id] = engine

    asyncio.create_task(_run_and_cleanup(device_id, engine, req.task, req.max_steps))

    return {"status": "started", "device_id": device_id, "task": req.task}


async def _run_and_cleanup(device_id: int, engine: AgentEngine, task: str, max_steps: int):
    try:
        result = await engine.run(task, max_steps)
        logger.info("Agent on device %d completed: %s", device_id, result.get("completed"))
    except Exception as e:
        logger.error("Agent on device %d crashed: %s", device_id, e)
    finally:
        _active_agents.pop(device_id, None)


@router.post("/devices/{device_id}/stop")
async def stop_agent(device_id: int, _=Depends(verify_token)):
    engine = _active_agents.pop(device_id, None)
    if not engine:
        raise HTTPException(404, "No agent running on this device")
    engine.stop()
    return {"status": "stopping", "device_id": device_id}


@router.get("/devices/{device_id}/status")
async def agent_status(device_id: int, _=Depends(verify_token)):
    engine = _active_agents.get(device_id)
    if not engine:
        return {"running": False, "device_id": device_id}
    return {
        "running": True,
        "device_id": device_id,
        "steps_done": len(engine._history),
        "last_action": engine._history[-1].action if engine._history else None,
    }


@router.get("/running")
async def list_running_agents(_=Depends(verify_token)):
    return {
        "agents": [
            {
                "device_id": did,
                "steps_done": len(eng._history),
                "last_action": eng._history[-1].action if eng._history else None,
            }
            for did, eng in _active_agents.items()
        ]
    }
