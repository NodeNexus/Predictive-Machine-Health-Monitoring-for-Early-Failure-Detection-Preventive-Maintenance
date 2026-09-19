"""Tests for GET /api/demo/thermal-video - streams the currently active
demo session's thermal source file for the dashboard's visible <video>
element. Pure API-level tests: no browser, no real video decoding.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.demo_runner import demo_runner


def test_thermal_video_returns_404_when_no_session_running():
    with TestClient(app) as client:
        assert demo_runner.is_running is False
        resp = client.get("/api/demo/thermal-video")
        assert resp.status_code == 404
        assert "no active" in resp.json()["detail"].lower()


def test_thermal_video_returns_404_when_session_has_no_thermal_source(tmp_path):
    import asyncio

    from app.database.models import Machine
    from app.database.session import SessionLocal, init_db
    from app.models.schemas import DemoStartRequest

    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Thermal Video Test - no thermal")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    wav_path = tmp_path / "silence.wav"
    import wave

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    async def scenario():
        await demo_runner.start(DemoStartRequest(machine_id=machine_id, acoustic_source=str(wav_path)))
        with TestClient(app) as client:
            resp = client.get("/api/demo/thermal-video")
            assert resp.status_code == 404
            assert "no active thermal" in resp.json()["detail"].lower()
        await demo_runner.stop()

    asyncio.run(scenario())


def test_thermal_video_streams_the_active_session_file():
    import asyncio

    from app.core.config import settings
    from app.database.models import Machine
    from app.database.session import SessionLocal, init_db
    from app.models.schemas import DemoStartRequest

    thermal_path = settings.video_dir / "1.mp4"
    assert thermal_path.is_file(), "expected the real demo thermal video to exist"

    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Thermal Video Test - streams file")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    async def scenario():
        await demo_runner.start(DemoStartRequest(machine_id=machine_id, thermal_source=str(thermal_path)))
        with TestClient(app) as client:
            resp = client.get("/api/demo/thermal-video")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "video/mp4"
            assert "attachment" not in resp.headers.get("content-disposition", "")
            assert len(resp.content) == thermal_path.stat().st_size
        await demo_runner.stop()

    asyncio.run(scenario())


def test_thermal_video_supports_range_requests():
    import asyncio

    from app.core.config import settings
    from app.database.models import Machine
    from app.database.session import SessionLocal, init_db
    from app.models.schemas import DemoStartRequest

    thermal_path = settings.video_dir / "1.mp4"

    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Thermal Video Test - range")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    async def scenario():
        await demo_runner.start(DemoStartRequest(machine_id=machine_id, thermal_source=str(thermal_path)))
        with TestClient(app) as client:
            resp = client.get("/api/demo/thermal-video", headers={"Range": "bytes=0-1023"})
            assert resp.status_code == 206
            assert resp.headers.get("content-range", "").startswith("bytes 0-1023/")
            assert len(resp.content) == 1024
        await demo_runner.stop()

    asyncio.run(scenario())
