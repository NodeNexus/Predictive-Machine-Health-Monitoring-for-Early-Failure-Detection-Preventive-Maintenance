"""Thermal demo evidence: saved evaluation endpoint, held-out labels in the image feed,
and the catalogue restriction on the streamed video."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.paths import REPO_ROOT
from app.main import app
from app.models.schemas import DemoStartRequest
from app.services.demo_runner import demo_runner


def test_thermal_evaluation_matches_the_saved_artifact():
    artifact = json.loads((REPO_ROOT / "models" / "thermal" / "test_evaluation.json").read_text(encoding="utf-8"))
    with TestClient(app) as client:
        body = client.get("/api/demo/thermal-evaluation").json()
    for key in ("accuracy", "macro_f1", "top3_accuracy", "test_count"):
        assert body[key] == artifact[key]
    assert body["model_version"] == "thermal-v1"


def test_image_feed_carries_the_known_test_label():
    with TestClient(app) as client:
        feed = client.get("/api/demo/thermal-image-feed").json()
    assert feed and all(entry["true_class"] in {"CFL", "CML", "CNL", "HFL", "HML", "HNL"} for entry in feed)
    assert all(entry["image_id"].startswith(entry["true_class"]) for entry in feed)


def test_thermal_video_is_served_only_for_catalogued_videos():
    uncatalogued = settings.video_dir / "6.mp4"  # deliberately absent from the machine-video catalogue
    if not uncatalogued.is_file():
        pytest.skip("demo video 6 not present in this environment")

    async def scenario():
        with TestClient(app) as client:
            machine = client.post("/api/machines", json={"machine_name": "Catalogue Test"}).json()
            await demo_runner.start(DemoStartRequest(machine_id=machine["machine_id"], thermal_source=str(uncatalogued)))
            try:
                return client.get("/api/demo/thermal-video").status_code
            finally:
                await demo_runner.stop()

    assert asyncio.run(scenario()) == 403


def test_browser_preview_copy_is_streamed_when_configured(tmp_path, monkeypatch):
    original = settings.video_dir / "1.mp4"
    if not original.is_file():
        pytest.skip("demo video 1 not present in this environment")
    (tmp_path / "1.mp4").write_bytes(b"PREVIEW-COPY")
    monkeypatch.setattr(settings, "video_preview_dir", tmp_path)

    async def scenario():
        with TestClient(app) as client:
            machine = client.post("/api/machines", json={"machine_name": "Preview Test"}).json()
            await demo_runner.start(DemoStartRequest(machine_id=machine["machine_id"], thermal_source=str(original)))
            try:
                return client.get("/api/demo/thermal-video").content
            finally:
                await demo_runner.stop()

    assert asyncio.run(scenario()) == b"PREVIEW-COPY"


def test_gate_passes_the_raw_best_guess_without_changing_the_reliable_class():
    from app.pipelines.thermal.confidence_gate import CONFIDENCE_THRESHOLD, apply_confidence_gate

    low = apply_confidence_gate({"predicted_class": "HFL", "confidence": CONFIDENCE_THRESHOLD - 0.01}, "v1")
    assert low["ml_prediction"] is None and low["ml_reliability"] == "low"  # still gated
    assert low["ml_top_class"] == "HFL"  # the real best guess is visible, marked by the unchanged gate result
    high = apply_confidence_gate({"predicted_class": "HFL", "confidence": CONFIDENCE_THRESHOLD}, "v1")
    assert high["ml_prediction"] == "HFL" and high["ml_top_class"] == "HFL"
    assert apply_confidence_gate(None, "v1")["ml_top_class"] is None
