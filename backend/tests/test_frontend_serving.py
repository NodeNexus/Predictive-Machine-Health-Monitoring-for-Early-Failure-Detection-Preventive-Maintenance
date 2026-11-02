"""Opt-in single-origin serving: the built dashboard at "/" without shadowing the API or the WebSocket."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app, mount_frontend


def test_api_only_by_default():
    with TestClient(app) as client:
        assert client.get("/").status_code == 404  # unchanged development behaviour
        assert client.get("/api/health").status_code == 200


def test_mounted_dashboard_does_not_shadow_api_or_websocket(tmp_path):
    (tmp_path / "index.html").write_text("<title>dashboard</title>", encoding="utf-8")
    from app.api import routes_health, websocket

    served = FastAPI()
    served.include_router(routes_health.router)
    served.include_router(websocket.router)
    assert mount_frontend(served, tmp_path) is True
    with TestClient(served) as client:
        assert "dashboard" in client.get("/").text
        assert client.get("/api/health").json()["status"] == "ok"
        with client.websocket_connect("/ws/telemetry"):
            pass  # the socket route is still reachable behind the "/" mount


def test_missing_build_is_reported_not_fatal(tmp_path):
    assert mount_frontend(FastAPI(), tmp_path) is False
