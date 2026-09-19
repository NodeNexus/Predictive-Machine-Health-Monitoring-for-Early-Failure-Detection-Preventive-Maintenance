from fastapi.testclient import TestClient

from app.main import app
from app.pipelines.common.interfaces import SlidingWindowBuffer
import numpy as np


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["app"] == "IDEA LAB"


def test_machine_crud_and_status():
    with TestClient(app) as client:
        create_resp = client.post("/api/machines", json={"machine_name": "Test Pump"})
        assert create_resp.status_code == 201
        machine = create_resp.json()
        machine_id = machine["machine_id"]
        assert machine["baseline_status"] == "not_calibrated"

        list_resp = client.get("/api/machines")
        assert any(m["machine_id"] == machine_id for m in list_resp.json())

        status_resp = client.get(f"/api/machines/{machine_id}/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["status"] == "unknown"
        assert set(status["missing_modalities"]) == {"thermal", "vibration", "acoustic"}


def test_machine_events_endpoint_starts_empty():
    with TestClient(app) as client:
        machine = client.post("/api/machines", json={"machine_name": "Events Test"}).json()
        resp = client.get(f"/api/machines/{machine['machine_id']}/events")
        assert resp.status_code == 200
        assert resp.json() == []

        missing = client.get("/api/machines/does-not-exist/events")
        assert missing.status_code == 404


def test_datasets_start_empty():
    with TestClient(app) as client:
        assert client.get("/api/datasets").json() == []


def test_devices_reflects_real_probe_not_fabricated_data():
    # Phase 10: /api/devices runs a real hardware probe every call, so it
    # is never empty - but in a sandboxed CI environment with no attached
    # sensors, everything should honestly report "not_connected".
    with TestClient(app) as client:
        devices = client.get("/api/devices").json()
        assert len(devices) >= 3
        assert all(d["status"] in ("connected", "not_connected", "error") for d in devices)


def test_demo_lifecycle():
    with TestClient(app) as client:
        machine = client.post("/api/machines", json={"machine_name": "Demo Machine"}).json()

        status = client.get("/api/demo/status").json()
        assert status["running"] is False

        start = client.post(
            "/api/demo/start",
            json={"machine_id": machine["machine_id"], "thermal_source": "VIDEO/sample.mp4"},
        )
        assert start.status_code == 200
        assert start.json()["running"] is True

        conflict = client.post("/api/demo/start", json={"machine_id": machine["machine_id"]})
        assert conflict.status_code == 409

        stop = client.post("/api/demo/stop")
        assert stop.json()["running"] is False


def test_sliding_window_buffer():
    buf = SlidingWindowBuffer(window_size=10, hop_size=5)
    windows = buf.push(np.arange(12, dtype=np.float64))
    assert len(windows) == 1
    assert list(windows[0]) == list(range(10))

    windows2 = buf.push(np.arange(12, 22, dtype=np.float64))
    assert len(windows2) >= 1

    remainder = buf.flush()
    assert remainder is None or len(remainder) < 10
