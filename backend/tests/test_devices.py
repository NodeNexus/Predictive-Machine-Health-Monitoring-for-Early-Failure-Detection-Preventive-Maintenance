from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.models import DeviceDefinition
from app.database.session import SessionLocal, init_db
from app.devices.discovery import discover_all, probe_microphones, probe_vibration_sensors
from app.devices.registry import sync_devices
from app.main import app


def test_discover_all_returns_one_entry_per_type_at_minimum():
    results = discover_all()
    types = {r.device_type for r in results}
    assert types == {"thermal_camera", "vibration_sensor", "microphone"}


def test_probe_vibration_and_microphone_are_honestly_not_connected():
    # No DAQ/audio-capture backend is integrated - these must never claim
    # "connected" since there's no way to actually verify hardware.
    for result in [*probe_vibration_sensors(), *probe_microphones()]:
        assert result.status == "not_connected"
        assert result.note is not None


def test_sync_devices_is_idempotent():
    init_db()
    db = SessionLocal()
    try:
        first_pass = sync_devices(db)
        first_count = len(first_pass)
        second_pass = sync_devices(db)
        assert len(second_pass) == first_count  # no duplicate rows created

        all_rows = db.scalars(select(DeviceDefinition)).all()
        assert len(all_rows) == first_count
    finally:
        db.close()


def test_devices_endpoint_returns_real_probe_results():
    with TestClient(app) as client:
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        devices = resp.json()
        types = {d["device_type"] for d in devices}
        assert "vibration_sensor" in types
        assert "microphone" in types
        assert "thermal_camera" in types
        for d in devices:
            assert d["status"] in ("connected", "not_connected", "error")
