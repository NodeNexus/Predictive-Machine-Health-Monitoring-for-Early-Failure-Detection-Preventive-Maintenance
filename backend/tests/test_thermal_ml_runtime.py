"""Tests for the runtime ML integration (backend/app/pipelines/thermal/
ml_model.py + confidence_gate.py) - separate from the training-side tests
in test_thermal_ml.py. Verifies the strict architecture rule: ML failures
must never propagate as exceptions, and the confidence gate must behave
exactly as documented.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.pipelines.thermal.confidence_gate import CONFIDENCE_THRESHOLD, apply_confidence_gate
from app.pipelines.thermal.ml_model import ThermalMLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CHECKPOINT = REPO_ROOT / "models" / "thermal" / "thermal_mobilenetv3_small_v1.pt"

model_available = pytest.mark.skipif(
    not MODEL_CHECKPOINT.is_file(), reason="Trained thermal model checkpoint not present in this environment"
)


@model_available
def test_model_loads_successfully():
    model = ThermalMLModel()
    assert model.available is True
    assert len(model.class_names) == 6
    assert model.model_version is not None


@model_available
def test_valid_frame_produces_prediction():
    model = ThermalMLModel()
    frame = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
    result = model.predict(frame)
    assert result is not None
    assert result["predicted_class"] in model.class_names
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["top_predictions"]) == 3


def test_model_unavailable_when_checkpoint_missing(tmp_path):
    model = ThermalMLModel(checkpoint_path=tmp_path / "nope.pt", metadata_path=tmp_path / "nope.json")
    assert model.available is False
    # predict() must not raise even though the model never loaded
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    assert model.predict(frame) is None


@model_available
def test_inference_failure_on_malformed_input_does_not_raise():
    model = ThermalMLModel()
    malformed = np.zeros((5,), dtype=np.uint8)  # wrong shape entirely
    result = model.predict(malformed)
    assert result is None  # caught internally, not propagated


def test_confidence_gate_passes_high_confidence_prediction():
    prediction = {
        "predicted_class": "CML",
        "confidence": 0.942,
        "top_predictions": [{"class": "CML", "confidence": 0.942}],
        "model_version": "thermal_mobilenetv3_small_v1",
    }
    gated = apply_confidence_gate(prediction, model_version="thermal_mobilenetv3_small_v1")
    assert gated["ml_prediction"] == "CML"
    assert gated["ml_confidence"] == 0.942
    assert gated["ml_condition"] == "Corroded Bearing"
    assert gated["ml_load_context"] == "Medium"
    assert gated["ml_reliability"] == "high"


def test_confidence_gate_suppresses_low_confidence_prediction_but_keeps_raw_confidence():
    prediction = {
        "predicted_class": "HFL",
        "confidence": 0.482,
        "top_predictions": [],
        "model_version": "thermal_mobilenetv3_small_v1",
    }
    gated = apply_confidence_gate(prediction, model_version="thermal_mobilenetv3_small_v1")
    assert gated["ml_prediction"] is None
    assert gated["ml_condition"] is None
    assert gated["ml_load_context"] is None
    assert gated["ml_reliability"] == "low"
    assert gated["ml_confidence"] == 0.482  # raw confidence preserved even when suppressed


def test_confidence_gate_handles_unavailable_model():
    gated = apply_confidence_gate(None, model_version="thermal_mobilenetv3_small_v1")
    assert gated["ml_prediction"] is None
    assert gated["ml_confidence"] is None
    assert gated["ml_reliability"] == "unavailable"
    assert gated["model_version"] == "thermal_mobilenetv3_small_v1"


def test_telemetry_payload_accepts_thermal_block_with_ml_fields_merged():
    """Confirms the existing TelemetryPayload schema (thermal: dict[str, Any])
    is compatible with a thermal block carrying both the pre-existing
    deterministic fields and the new ML fields merged in - exactly what
    demo_runner._telemetry_block produces."""
    from datetime import datetime, timezone

    from app.models.schemas import TelemetryPayload

    thermal_block = {
        "source": "demo:some_video.mp4",
        "mean_intensity": 120.5,
        "max_intensity": 255.0,
        "hotspot_area_fraction": 0.01,
        # merged-in ML fields:
        "ml_prediction": "CML",
        "ml_confidence": 0.942,
        "ml_condition": "Corroded Bearing",
        "ml_load_context": "Medium",
        "ml_reliability": "high",
        "model_version": "thermal_mobilenetv3_small_v1",
    }
    payload = TelemetryPayload(
        timestamp=datetime.now(timezone.utc),
        machine_id="m1",
        mode="demo",
        thermal=thermal_block,
        vibration=None,
        acoustic=None,
        health=None,
        events=[],
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["thermal"]["mean_intensity"] == 120.5  # existing field intact
    assert dumped["thermal"]["ml_prediction"] == "CML"  # new field present
    assert dumped["thermal"]["ml_reliability"] == "high"


def test_confidence_gate_threshold_boundary():
    just_below = {"predicted_class": "HNL", "confidence": CONFIDENCE_THRESHOLD - 0.01, "model_version": "v1"}
    just_above = {"predicted_class": "HNL", "confidence": CONFIDENCE_THRESHOLD + 0.01, "model_version": "v1"}
    assert apply_confidence_gate(just_below, "v1")["ml_reliability"] == "low"
    assert apply_confidence_gate(just_above, "v1")["ml_reliability"] == "high"
