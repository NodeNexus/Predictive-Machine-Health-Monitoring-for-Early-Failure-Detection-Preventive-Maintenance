from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.database.models import AnomalyEvent, HealthHistory, Machine
from app.models.schemas import MachineCreate, MachineHealthState, MachineOut

router = APIRouter(prefix="/api/machines", tags=["machines"])


@router.get("", response_model=list[MachineOut])
def list_machines(db: Session = Depends(get_db)) -> list[Machine]:
    return list(db.scalars(select(Machine)))


@router.post("", response_model=MachineOut, status_code=201)
def create_machine(payload: MachineCreate, db: Session = Depends(get_db)) -> Machine:
    machine = Machine(**payload.model_dump())
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: str, db: Session = Depends(get_db)) -> Machine:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine


@router.get("/{machine_id}/status")
def get_machine_status(machine_id: str, db: Session = Depends(get_db)) -> MachineHealthState:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    latest = db.scalars(
        select(HealthHistory)
        .where(HealthHistory.machine_id == machine_id)
        .order_by(HealthHistory.timestamp.desc())
        .limit(1)
    ).first()

    if latest is None:
        # Technically honest: no processing has run yet for this machine.
        return MachineHealthState(
            machine_id=machine_id,
            timestamp=machine.created_at,
            status="unknown",
            missing_modalities=["thermal", "vibration", "acoustic"],
        )

    return MachineHealthState(
        machine_id=machine_id,
        timestamp=latest.timestamp,
        health_score=latest.health_score,
        status=latest.status,  # type: ignore[arg-type]
        confidence=latest.confidence,
        evidence=(latest.evidence or {}).get("evidence", []),
        modality_contributions=(latest.evidence or {}).get("modality_contributions", {}),
    )


@router.get("/{machine_id}/history")
def get_machine_history(machine_id: str, limit: int = 200, db: Session = Depends(get_db)) -> list[dict]:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    records = db.scalars(
        select(HealthHistory)
        .where(HealthHistory.machine_id == machine_id)
        .order_by(HealthHistory.timestamp.desc())
        .limit(limit)
    )
    return [
        {
            "timestamp": r.timestamp,
            "health_score": r.health_score,
            "status": r.status,
            "confidence": r.confidence,
        }
        for r in records
    ]


@router.get("/{machine_id}/events")
def get_machine_events(machine_id: str, limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    machine = db.get(Machine, machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")

    records = db.scalars(
        select(AnomalyEvent)
        .where(AnomalyEvent.machine_id == machine_id)
        .order_by(AnomalyEvent.started_at.desc())
        .limit(limit)
    )
    return [
        {
            "event_id": r.event_id,
            "started_at": r.started_at,
            "resolved_at": r.resolved_at,
            "severity": r.severity,
            "modality_contributions": r.modality_contributions,
            "evidence": r.evidence,
        }
        for r in records
    ]
