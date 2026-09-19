from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.database.models import DeviceDefinition
from app.devices.registry import sync_devices
from app.models.schemas import DeviceStatusOut

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceStatusOut])
def list_devices(db: Session = Depends(get_db)) -> list[DeviceDefinition]:
    """Re-probes hardware on every call (cheap - a handful of camera-index
    opens) and returns the current, real state. Devices with no available
    probing backend (vibration, microphone) honestly report
    "not_connected" with a note explaining why, never a fabricated
    "connected" state.
    """
    return sync_devices(db)
