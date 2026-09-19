"""Tests for the Acoustic ML V1 runtime integration
(backend/app/pipelines/acoustic/ml_model.py + confidence_gate.py +
demo_runner._acoustic_loop's ML wiring) - separate from the training-side
tests in the ml/acoustic/ package. Verifies the strict architecture rule:
ML failures must never propagate as exceptions, the deterministic
AcousticAnalyzer output is never altered by ML, and the confidence gate
behaves exactly as documented.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from app.pipelines.acoustic.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    apply_confidence_gate,
    to_telemetry_fields,
)
from app.pipelines.acoustic.ml_model import AcousticMLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = REPO_ROOT / "models" / "acoustic" / "acoustic_baseline_v1.joblib"
DATASET_DIR = REPO_ROOT / "DATASET" / "bearing" / "bearing"

model_available = pytest.mark.skipif(
    not MODEL_PATH.is_file(), reason="Trained acoustic model not present in this environment"
)
dataset_available = pytest.mark.skipif(
    not DATASET_DIR.is_dir(), reason="Bearing acoustic dataset not present in this environment"
)


def _write_synthetic_wav(path: Path, seconds: float = 10.0, sample_rate: int = 16000) -> None:
    rng = np.random.default_rng(0)
    n_samples = int(seconds * sample_rate)
    data = (rng.normal(0, 0.05, size=n_samples) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())


@model_available
def test_model_loads_once_and_successfully():
    model = AcousticMLModel()
    assert model.available is True
    assert model.class_names == ["normal", "anomaly"]
    assert model.model_version is not None
    assert len(model.feature_columns) == 61


@model_available
def test_valid_whole_clip_produces_prediction(tmp_path):
    wav_path = tmp_path / "synthetic.wav"
    _write_synthetic_wav(wav_path)
    model = AcousticMLModel()
    result = model.predict(wav_path)
    assert result is not None
    assert result["predicted_class"] in model.class_names
    assert 0.0 <= result["confidence"] <= 1.0
    assert set(result["probabilities"]) == set(model.class_names)


def test_model_unavailable_when_files_missing(tmp_path):
    model = AcousticMLModel(model_path=tmp_path / "nope.joblib", metadata_path=tmp_path / "nope.json")
    assert model.available is False
    wav_path = tmp_path / "synthetic.wav"
    _write_synthetic_wav(wav_path)
    assert model.predict(wav_path) is None


@model_available
def test_feature_mismatch_missing_file_is_handled_safely():
    model = AcousticMLModel()
    result = model.predict(Path("/definitely/does/not/exist.wav"))
    assert result is None  # caught internally, not propagated


@dataset_available
@model_available
def test_real_normal_and_anomaly_files_produce_predictions():
    normal_files = sorted((DATASET_DIR / "test").glob("section_00_source_test_normal_*.wav"))
    anomaly_files = sorted((DATASET_DIR / "test").glob("section_00_source_test_anomaly_*.wav"))
    assert normal_files and anomaly_files

    model = AcousticMLModel()
    normal_result = model.predict(normal_files[0])
    anomaly_result = model.predict(anomaly_files[0])
    assert normal_result is not None
    assert anomaly_result is not None
    assert normal_result["predicted_class"] in model.class_names
    assert anomaly_result["predicted_class"] in model.class_names


def test_confidence_gate_passes_high_confidence_prediction():
    prediction = {"predicted_class": "anomaly", "confidence": 0.947, "model_version": "acoustic-v1"}
    gated = apply_confidence_gate(prediction, model_version="acoustic-v1")
    assert gated["accepted"] is True
    assert gated["prediction"] == "anomaly"
    assert gated["reliability"] == "high"

    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] == "anomaly"
    assert telemetry["ml_confidence"] == 0.947
    assert telemetry["ml_reliability"] == "high"
    assert telemetry["ml_model_version"] == "acoustic-v1"


def test_confidence_gate_suppresses_low_confidence_prediction_but_keeps_raw_confidence():
    prediction = {"predicted_class": "anomaly", "confidence": 0.673, "model_version": "acoustic-v1"}
    gated = apply_confidence_gate(prediction, model_version="acoustic-v1")
    assert gated["accepted"] is False
    assert gated["reliability"] == "low"

    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] is None  # never a definitive anomaly diagnosis when suppressed
    assert telemetry["ml_confidence"] == 0.673  # raw confidence preserved even when suppressed
    assert telemetry["ml_reliability"] == "low"


def test_confidence_gate_handles_unavailable_model():
    gated = apply_confidence_gate(None, model_version="acoustic-v1")
    telemetry = to_telemetry_fields(gated)
    assert telemetry["ml_prediction"] is None
    assert telemetry["ml_confidence"] is None
    assert telemetry["ml_reliability"] == "unavailable"
    assert telemetry["ml_model_version"] == "acoustic-v1"


def test_confidence_gate_threshold_boundary():
    just_below = {"predicted_class": "normal", "confidence": CONFIDENCE_THRESHOLD - 0.01}
    just_above = {"predicted_class": "normal", "confidence": CONFIDENCE_THRESHOLD + 0.01}
    assert apply_confidence_gate(just_below)["reliability"] == "low"
    assert apply_confidence_gate(just_above)["reliability"] == "high"


def test_telemetry_payload_accepts_acoustic_block_with_ml_fields_merged():
    """Confirms the existing TelemetryPayload schema (acoustic: dict[str, Any])
    is compatible with an acoustic block carrying both the pre-existing
    deterministic fields and the new ML fields merged in - exactly what
    demo_runner._telemetry_block produces."""
    from datetime import datetime, timezone

    from app.models.schemas import TelemetryPayload

    acoustic_block = {
        "source": "demo:section_00_source_test_anomaly_0000_vel_6.wav",
        "rms": 0.021,
        "spectral_centroid": 2863.7,
        # merged-in ML fields:
        "ml_prediction": "anomaly",
        "ml_confidence": 0.947,
        "ml_reliability": "high",
        "ml_model_version": "acoustic-v1",
    }
    payload = TelemetryPayload(
        timestamp=datetime.now(timezone.utc),
        machine_id="m1",
        mode="demo",
        thermal=None,
        vibration=None,
        acoustic=acoustic_block,
        health=None,
        events=[],
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["acoustic"]["rms"] == 0.021  # existing deterministic field intact
    assert dumped["acoustic"]["ml_prediction"] == "anomaly"  # new field present
    assert dumped["acoustic"]["ml_reliability"] == "high"


@model_available
def test_deterministic_acoustic_analyzer_unaffected_by_ml_call(tmp_path):
    """The ML model must never mutate anything the deterministic
    AcousticAnalyzer produces - it reads the file independently."""
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from app.pipelines.acoustic.analyzer import AcousticAnalyzer
    from app.pipelines.common.interfaces import SampleChunk
    from datetime import datetime, timezone

    wav_path = tmp_path / "synthetic.wav"
    _write_synthetic_wav(wav_path, seconds=2.0)

    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0

    def _run_analyzer() -> list[dict]:
        analyzer = AcousticAnalyzer(sample_rate=16000.0, window_seconds=1.0, overlap=0.5)
        chunk = SampleChunk(samples=samples.copy(), sample_rate=16000.0, timestamp=datetime.now(timezone.utc), metadata={})
        evidence = analyzer.process_chunk(chunk, "test-source")
        return [e.model_dump(mode="json", exclude={"timestamp"}) for e in evidence]

    before_dump = _run_analyzer()

    model = AcousticMLModel()
    model.predict(wav_path)  # runs ML inference on the same file, independently

    after_dump = _run_analyzer()  # fresh analyzer, same input - must produce identical deterministic output
    assert before_dump == after_dump
