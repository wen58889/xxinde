from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.device import DeviceStatus
from app.models.task import TaskStatus


# ── Device ──
class DeviceOut(BaseModel):
    id: int
    ip: str
    hostname: str
    status: DeviceStatus
    firmware_version: Optional[str] = None
    last_heartbeat: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Task ──
class ExecuteRequest(BaseModel):
    action: str
    params: dict = {}
    sync: bool = False


class NaturalTaskRequest(BaseModel):
    instruction: str
    device_id: Optional[int] = None


class RunYamlRequest(BaseModel):
    yaml_content: str


class BatchRunRequest(BaseModel):
    device_ids: List[int]
    yaml_content: str


class VisionRequest(BaseModel):
    method: str  # find_icon | read_text | detect_anomaly | detect_targets
    params: dict = {}


class TaskOut(BaseModel):
    id: int
    device_id: int
    template_name: Optional[str] = None
    status: TaskStatus
    current_step: int = 0
    total_steps: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Template ──
class TemplateCreate(BaseModel):
    app_name: str
    name: str
    yaml_content: str


class TemplateOut(BaseModel):
    id: int
    app_name: str
    name: str
    yaml_content: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Calibration ──
class CalibrationRequest(BaseModel):
    pixel_points: List[List[float]]
    mech_points: List[List[float]]
    offset_x: float = 0.0
    offset_y: float = 0.0


class OffsetRequest(BaseModel):
    offset_x: float
    offset_y: float


class CalibrationOut(BaseModel):
    id: int
    device_id: int
    pixel_points: List[List[float]]
    mech_points: List[List[float]]
    offset_x: float
    offset_y: float

    model_config = {"from_attributes": True}


# ── Auth ──
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Generic ──
class MessageOut(BaseModel):
    message: str
