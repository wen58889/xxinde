from datetime import datetime
from sqlalchemy import Integer, Float, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CalibrationData(Base):
    __tablename__ = "calibrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id"), unique=True, nullable=False
    )
    pixel_points: Mapped[dict] = mapped_column(JSON, nullable=False)
    mech_points: Mapped[dict] = mapped_column(JSON, nullable=False)
    offset_x: Mapped[float] = mapped_column(Float, default=0.0)
    offset_y: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
