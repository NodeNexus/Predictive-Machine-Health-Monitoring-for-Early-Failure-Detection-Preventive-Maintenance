"""Persists scanned dataset manifests to the JSON manifest file and DB registry."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DatasetRegistry
from app.datasets.manifest import DatasetManifestEntry


def write_manifest_file(entries: list[DatasetManifestEntry], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_count": len(entries),
        "datasets": [e.model_dump() for e in entries],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sync_to_db(entries: list[DatasetManifestEntry], db: Session, manifest_path: Path) -> None:
    for entry in entries:
        existing = db.scalars(
            select(DatasetRegistry).where(DatasetRegistry.dataset_name == entry.dataset_name)
        ).first()

        fields = dict(
            dataset_name=entry.dataset_name,
            machine_type=entry.machine_type,
            modality=entry.modality,
            path=entry.path,
            format=entry.format,
            sample_count=entry.sample_count,
            sample_rate=entry.sample_rate,
            channels=entry.channels,
            normal_count=entry.normal_count,
            anomaly_count=entry.anomaly_count,
            notes=entry.notes,
            manifest_path=str(manifest_path),
            scanned_at=datetime.now(timezone.utc),
        )

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(DatasetRegistry(**fields))

    db.commit()
