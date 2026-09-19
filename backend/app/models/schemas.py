"""Pydantic schemas for the REST API and WebSocket telemetry payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Modality = Literal["thermal", "vibration", "acoustic"]
HealthStatus = Literal["normal", "warning", "critical", "unknown"]


class MachineCreate(BaseModel):
    machine_name: str
    machine_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    rpm: float | None = None
    rated_power: float | None = None
    location: str | None = None
    sensor_configuration: dict[str, Any] | None = None


class MachineOut(MachineCreate):
    machine_id: str
    baseline_status: str
    monitoring_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceItem(BaseModel):
    modality: Modality
    feature: str
    value: float | None = None
    baseline_mean: float | None = None
    deviation: float | None = None
    note: str | None = None


class MachineHealthState(BaseModel):
    machine_id: str
    timestamp: datetime
    health_score: float | None = None
    status: HealthStatus = "unknown"
    severity: str | None = None
    confidence: float | None = None
    modality_contributions: dict[str, float] = Field(default_factory=dict)
    missing_modalities: list[Modality] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    model_version: str | None = None


class TelemetryPayload(BaseModel):
    timestamp: datetime
    machine_id: str
    mode: Literal["demo", "live"]
    thermal: dict[str, Any] | None = None
    vibration: dict[str, Any] | None = None
    acoustic: dict[str, Any] | None = None
    health: MachineHealthState | None = None
    ml_fusion: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class DatasetInfo(BaseModel):
    dataset_id: str
    dataset_name: str
    machine_type: str | None = None
    modality: str
    path: str
    format: str | None = None
    sample_count: int | None = None
    sample_rate: float | None = None
    channels: int | None = None
    normal_count: int | None = None
    anomaly_count: int | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class DeviceStatusOut(BaseModel):
    device_id: str
    device_type: str
    machine_id: str | None = None
    connection_type: str | None = None
    status: Literal["connected", "not_connected", "error"]
    configuration: dict[str, Any] | None = None
    last_seen: datetime | None = None

    model_config = {"from_attributes": True}


class DemoStartRequest(BaseModel):
    machine_id: str
    thermal_source: str | None = None
    vibration_source: str | None = None
    vibration_channel: int = 0
    vibration_start_file: int | None = None
    vibration_end_file: int | None = None
    acoustic_source: str | None = None
    playback_speed: float = 1.0


class DemoStatusOut(BaseModel):
    running: bool
    machine_id: str | None = None
    session_id: str | None = None
    mode: Literal["demo"] = "demo"
    sources: dict[str, str | None] = Field(default_factory=dict)
    started_at: datetime | None = None
