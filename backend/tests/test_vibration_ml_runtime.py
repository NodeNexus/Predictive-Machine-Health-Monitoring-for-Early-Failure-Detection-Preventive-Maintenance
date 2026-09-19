"""Tests for the Vibration ML V1 runtime integration
(backend/app/pipelines/vibration/ml_model.py + confidence_gate.py +
demo_runner._vibration_loop's ML wiring) - separate from the training-side
tests in the ml/vibration/ package. Verifies the strict architecture rule:
ML failures must never propagate as exceptions, the deterministic
VibrationAnalyzer output is never altered by ML, and the confidence gate
behaves exactly as documented.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.pipelines.vibration.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    apply_confidence_gate,
    to_telemetry_fields,
)
from app.pipelines.vibration.features import extract_vibration_features
from app.pipelines.vibration.ml_model import VibrationMLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = REPO_ROOT / "models" / "vibration" / "vibration_baseline_v1.joblib"

model_available = pytest.mark.skipif(
    not MODEL_PATH.is_file(), reason="Trained vibration model not present in this environment"
)


def _real_features():
    """A real, physically-derived feature vector (synthetic waveform, not a
    stub) so tests exercise the actual VibrationFeatures object the model
    consumes at runtime."""
    rng = np.random.default_rng(42)
    window = rng.normal(0, 0.15, size=20480)
    return extract_vibration_features(window, sample_rate=20000.0)


@model_available
def test_model_loads_once_and_successfully():
    model = VibrationMLModel()
    assert model.available is True
    assert model.class_names == ["healthy", "degrading", "severe"]
    assert model.model_version is not None
    assert len(model.feature_columns) == 10


@model_available
def test_valid_feature_vector_produces_prediction():
    model = VibrationMLModel()
    result = model.predict(_real_features())
    assert result is not None
    assert result["predicted_class"] in model.class_names
    assert 0.0 <= result["confidence"] <= 1.0
    assert set(result["probabilities"]) == set(model.class_names)


def test_model_unavailable_when_files_missing(tmp_path):
    model = VibrationMLModel(model_path=tmp_path / "nope.joblib", metadata_path=tmp_path / "nope.json")
    assert model.available is False
    # predict() must not raise even though the model never loaded
    assert model.predict(_real_features()) is None


@model_available
def test_feature_mismatch_is_handled_safely():
    model = VibrationMLModel()

    class _WrongShape:
        pass  # missing every expected attribute - simulates a schema drift

    result = model.predict(_WrongShape())
    assert result is None  # caught internally, not propagated


def test_confidence_gate_passes_high_confidence_prediction():
    prediction = {"predicted_class": "degrading", "confidence": 0.974, "model_version": "vibration-v1"}
    gated = apply_confidence_gate(prediction, model_version="vibration-v1")
    assert gated["accepted"] is True
    assert gated["prediction"] == "degrading"
    assert gated["reliability"] == "high"

    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] == "degrading"
    assert telemetry["ml_confidence"] == 0.974
    assert telemetry["ml_reliability"] == "high"
    assert telemetry["ml_model_version"] == "vibration-v1"


def test_confidence_gate_suppresses_low_confidence_prediction_but_keeps_raw_confidence():
    prediction = {"predicted_class": "severe", "confidence": 0.67, "model_version": "vibration-v1"}
    gated = apply_confidence_gate(prediction, model_version="vibration-v1")
    assert gated["accepted"] is False
    assert gated["reliability"] == "low"

    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] is None  # never a definitive health state when suppressed
    assert telemetry["ml_confidence"] == 0.67  # raw confidence preserved even when suppressed
    assert telemetry["ml_reliability"] == "low"


def test_confidence_gate_handles_unavailable_model():
    gated = apply_confidence_gate(None, model_version="vibration-v1")
    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] is None
    assert telemetry["ml_confidence"] is None
    assert telemetry["ml_reliability"] == "unavailable"
    assert telemetry["ml_model_version"] == "vibration-v1"


def test_confidence_gate_threshold_boundary():
    just_below = {"predicted_class": "healthy", "confidence": CONFIDENCE_THRESHOLD - 0.01}
    just_above = {"predicted_class": "healthy", "confidence": CONFIDENCE_THRESHOLD + 0.01}
    assert apply_confidence_gate(just_below)["reliability"] == "low"
    assert apply_confidence_gate(just_above)["reliability"] == "high"


def test_telemetry_payload_accepts_vibration_block_with_ml_fields_merged():
    """Confirms the existing TelemetryPayload schema (vibration: dict[str, Any])
    is compatible with a vibration block carrying both the pre-existing
    deterministic fields and the new ML fields merged in - exactly what
    demo_runner._telemetry_block produces."""
    from datetime import datetime, timezone

    from app.models.schemas import TelemetryPayload

    vibration_block = {
        "source": "demo:DATASET/IMS/IMS/1st_test/1st_test#ch4",
        "rms": 0.593,
        "kurtosis": 8.9,
        "crest_factor": 4.1,
        # merged-in ML fields:
        "ml_prediction": "degrading",
        "ml_confidence": 0.974,
        "ml_reliability": "high",
        "ml_model_version": "vibration-v1",
    }
    payload = TelemetryPayload(
        timestamp=datetime.now(timezone.utc),
        machine_id="m1",
        mode="demo",
        thermal=None,
        vibration=vibration_block,
        acoustic=None,
        health=None,
        events=[],
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["vibration"]["rms"] == 0.593  # existing deterministic field intact
    assert dumped["vibration"]["ml_prediction"] == "degrading"  # new field present
    assert dumped["vibration"]["ml_reliability"] == "high"


@model_available
def test_deterministic_vibration_features_unaffected_by_ml_call():
    """The ML model must never mutate the VibrationFeatures object it
    consumes - the deterministic analyzer output stays authoritative."""
    features = _real_features()
    before = features.model_dump(mode="json")
    model = VibrationMLModel()
    model.predict(features)
    after = features.model_dump(mode="json")
    assert before == after
