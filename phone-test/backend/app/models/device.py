from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DeviceStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    SUSPECT = "SUSPECT"
    OFFLINE = "OFFLINE"
    RECOVERING = "RECOVERING"
    ESTOP = "ESTOP"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus), default=DeviceStatus.OFFLINE, nullable=False
    )
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime)
    missed_heartbeats: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
