"""Persists device discovery results to the `devices` DB table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DeviceDefinition
from app.devices.discovery import discover_all


def sync_devices(db: Session) -> list[DeviceDefinition]:
    results = discover_all()
    now = datetime.now(timezone.utc)

    same_type_devices = {
        result.device_type: list(
            db.scalars(select(DeviceDefinition).where(DeviceDefinition.device_type == result.device_type))
        )
        for result in results
    }

    for result in results:
        configuration = {**result.configuration, "identifier": result.identifier, "note": result.note}
        existing = next(
            (
                d
                for d in same_type_devices[result.device_type]
                if (d.configuration or {}).get("identifier") == result.identifier
            ),
            None,
        )

        if existing:
            existing.connection_type = result.connection_type
            existing.status = result.status
            existing.configuration = configuration
            existing.last_seen = now
        else:
            db.add(
                DeviceDefinition(
                    device_type=result.device_type,
                    connection_type=result.connection_type,
                    status=result.status,
                    configuration=configuration,
                    last_seen=now,
                )
            )

    db.commit()
    return list(db.scalars(select(DeviceDefinition)))
