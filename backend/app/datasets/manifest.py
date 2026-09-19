"""Manifest data model shared by the scanner and the dataset registry."""
from __future__ import annotations

from pydantic import BaseModel


class DatasetManifestEntry(BaseModel):
    dataset_name: str
    machine_type: str | None = None
    modality: str  # thermal | vibration | acoustic | other
    path: str
    format: str | None = None
    sample_count: int | None = None
    duration_seconds: float | None = None
    sample_rate: float | None = None
    channels: int | None = None
    label_categories: list[str] = []
    normal_count: int | None = None
    anomaly_count: int | None = None
    notes: str | None = None
