"""SQLAlchemy ORM models.

Raw sensor data (audio/video/vibration) is never stored here - only
references/paths and derived metadata, per the data-handling policy.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Machine(Base):
    __tablename__ = "machines"

    machine_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    machine_name: Mapped[str] = mapped_column(String)
    machine_type: Mapped[str | None] = mapped_column(String, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    sensor_configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_status: Mapped[str] = mapped_column(String, default="not_calibrated")
    monitoring_status: Mapped[str] = mapped_column(String, default="stopped")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    baselines: Mapped[list["Baseline"]] = relationship(back_populates="machine")


class Baseline(Base):
    __tablename__ = "baselines"

    baseline_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"))
    modality: Mapped[str] = mapped_column(String)  # thermal | vibration | acoustic
    statistics: Mapped[dict] = mapped_column(JSON)  # mean/std/percentiles per feature
    observation_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    machine: Mapped[Machine] = relationship(back_populates="baselines")


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"))
    mode: Mapped[str] = mapped_column(String)  # demo | live
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_description: Mapped[str | None] = mapped_column(String, nullable=True)


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"))
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    severity: Mapped[str] = mapped_column(String)
    modality_contributions: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)


class HealthHistory(Base):
    __tablename__ = "health_history"

    record_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id"))
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DatasetRegistry(Base):
    __tablename__ = "dataset_registry"

    dataset_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_name: Mapped[str] = mapped_column(String)
    machine_type: Mapped[str | None] = mapped_column(String, nullable=True)
    modality: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    format: Mapped[str | None] = mapped_column(String, nullable=True)
    sample_count: Mapped[int | None] = mapped_column(nullable=True)
    sample_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    channels: Mapped[int | None] = mapped_column(nullable=True)
    normal_count: Mapped[int | None] = mapped_column(nullable=True)
    anomaly_count: Mapped[int | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    manifest_path: Mapped[str | None] = mapped_column(String, nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DeviceDefinition(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    device_type: Mapped[str] = mapped_column(String)  # thermal_camera | vibration_sensor | microphone
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String, nullable=True)  # usb | rtsp | serial | daq | network
    status: Mapped[str] = mapped_column(String, default="not_connected")
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
