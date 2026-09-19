"""Persists/loads BaselineStats to/from the `baselines` DB table."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.anomaly.baseline import BaselineStats
from app.database.models import Baseline, Machine


def save_baseline(db: Session, machine_id: str, stats: BaselineStats) -> None:
    existing = db.scalars(
        select(Baseline).where(Baseline.machine_id == machine_id, Baseline.modality == stats.modality)
    ).first()

    payload = stats.model_dump()
    if existing:
        existing.statistics = payload
        existing.observation_count = stats.observation_count
    else:
        db.add(
            Baseline(
                machine_id=machine_id,
                modality=stats.modality,
                statistics=payload,
                observation_count=stats.observation_count,
            )
        )

    machine = db.get(Machine, machine_id)
    if machine is not None:
        modalities_with_baseline = {
            b.modality for b in db.scalars(select(Baseline).where(Baseline.machine_id == machine_id))
        } | {stats.modality}
        machine.baseline_status = "calibrated" if modalities_with_baseline else "not_calibrated"

    db.commit()


def load_baseline(db: Session, machine_id: str, modality: str) -> BaselineStats | None:
    row = db.scalars(
        select(Baseline).where(Baseline.machine_id == machine_id, Baseline.modality == modality)
    ).first()
    if row is None:
        return None
    return BaselineStats.model_validate(row.statistics)
