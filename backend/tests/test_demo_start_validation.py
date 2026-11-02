"""POST /api/demo/start rejects sources that could never be replayed, instead of starting an empty session."""
from fastapi.testclient import TestClient

from app.main import app


def _machine(client: TestClient) -> str:
    return client.post("/api/machines", json={"machine_name": "Validation Test"}).json()["machine_id"]


def test_start_without_any_source_is_rejected():
    with TestClient(app) as client:
        resp = client.post("/api/demo/start", json={"machine_id": _machine(client)})
        assert resp.status_code == 400
        assert "at least one source" in resp.json()["detail"]
        assert client.get("/api/demo/status").json()["running"] is False


def test_start_with_missing_files_is_rejected_per_source():
    with TestClient(app) as client:
        machine_id = _machine(client)
        for field, label in [("thermal_source", "Thermal video"), ("acoustic_source", "Sound"), ("vibration_source", "Vibration")]:
            resp = client.post("/api/demo/start", json={"machine_id": machine_id, field: "does/not/exist"})
            assert resp.status_code == 422, field
            assert label in resp.json()["detail"]
        assert client.get("/api/demo/status").json()["running"] is False
