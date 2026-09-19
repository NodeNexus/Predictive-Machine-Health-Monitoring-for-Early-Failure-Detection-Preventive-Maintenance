from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.database.models import DatasetRegistry
from app.models.schemas import DatasetInfo

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetInfo])
def list_datasets(db: Session = Depends(get_db)) -> list[DatasetRegistry]:
    """Returns whatever the dataset scanner has actually registered.

    Empty until `scripts/scan_datasets.py` has been run (Phase 2) - this is
    the honest state, not a placeholder.
    """
    return list(db.scalars(select(DatasetRegistry)))
