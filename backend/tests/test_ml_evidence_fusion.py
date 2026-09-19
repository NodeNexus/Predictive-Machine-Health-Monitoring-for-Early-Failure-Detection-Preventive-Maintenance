"""Tests for Multimodal ML Evidence Fusion V1
(app.fusion.ml_evidence.fuse_thermal_vibration_acoustic). Pure unit tests
against the fusion function only - no model loading, no live integration,
no dependency on demo_runner or the dashboard.
"""
from __future__ import annotations

import json

import pytest

from app.fusion.ml_evidence import (
    AmbiguousAnomalyStrengthMapping,
    build_acoustic_evidence,
    build_thermal_evidence,
    build_vibration_evidence,
    fuse_thermal_vibration_acoustic,
)


def _thermal(prediction="HFL", confidence=0.9, condition="Healthy", load="Full", reliability="high"):
    return {
        "ml_prediction": prediction,
        "ml_confidence": confidence,
        "ml_condition": condition,
        "ml_load_context": load,
        "ml_reliability": reliability,
        "model_version": "thermal_mobilenetv3_small_v1",
    }


def _vibration(accepted=True, prediction="healthy", confidence=0.9, reliability="high"):
    return {
        "accepted": accepted,
        "prediction": prediction,
        "confidence": confidence,
        "reliability": reliability,
        "reason": "test",
        "model_version": "vibration-v1",
    }


def _acoustic(accepted=True, prediction="normal", confidence=0.9, reliability="high"):
    return {
        "accepted": accepted,
        "prediction": prediction,
        "confidence": confidence,
        "reliability": reliability,
        "reason": "test",
        "model_version": "acoustic-v1",
    }


# --- weighted average calculation / confidence propagation -----------------

def test_all_three_high_confidence_weighted_average():
    result = fuse_thermal_vibration_acoustic(
        _thermal(condition="Healthy", confidence=0.94),      # anomaly_strength=0.0
        _vibration(prediction="severe", confidence=0.97),     # anomaly_strength=1.0
        _acoustic(prediction="anomaly", confidence=0.95),      # anomaly_strength=1.0
    )
    expected_severity = (0.94 * 0.0 + 0.97 * 1.0 + 0.95 * 1.0) / (0.94 + 0.97 + 0.95)
    assert result["fused_severity"] == pytest.approx(expected_severity, abs=1e-4)
    assert result["fused_confidence"] == pytest.approx((0.94 + 0.97 + 0.95) / 3, abs=1e-4)
    assert result["reliability"] == "high"
    assert set(result["available_modalities"]) == {"thermal", "vibration", "acoustic"}
    assert result["model_type"] == "weighted_evidence_fusion"
    assert result["version"] == "fusion_v1"


def test_confidence_propagation_hand_checked_example_from_task():
    """Thermal: strength=0.8 conf=0.9 high. Vibration: strength=0.6 conf=0.8
    high. Acoustic: strength=1.0 conf=0.5 LOW -> contributes zero weight."""
    thermal = _thermal(condition="Corroded Bearing", confidence=0.9)  # anomaly_strength=1.0, not 0.8 exactly but we control via a custom evidence dict below
    # Build evidence directly at the common-schema level to hit exact 0.8/0.6/1.0 strengths from the task's example.
    thermal_evidence = {"available": True, "prediction": "x", "confidence": 0.9, "reliability": "high", "anomaly_strength": 0.8, "model_version": "t", "known_limitation": "x"}
    vibration_evidence = {"available": True, "prediction": "x", "confidence": 0.8, "reliability": "high", "anomaly_strength": 0.6, "model_version": "v", "known_limitation": "x"}
    acoustic_evidence = {"available": True, "prediction": "x", "confidence": 0.5, "reliability": "low", "anomaly_strength": 1.0, "model_version": "a", "known_limitation": "x"}

    from app.fusion.ml_evidence import _weight  # internal, but this is exactly the documented formula unit

    w_thermal = _weight(thermal_evidence)
    w_vibration = _weight(vibration_evidence)
    w_acoustic = _weight(acoustic_evidence)

    assert w_thermal == 0.9
    assert w_vibration == 0.8
    assert w_acoustic == 0.0  # low reliability -> zero weight, regardless of its 0.5 raw confidence

    fused_severity = (w_thermal * 0.8 + w_vibration * 0.6) / (w_thermal + w_vibration)
    assert fused_severity == pytest.approx((0.9 * 0.8 + 0.8 * 0.6) / (0.9 + 0.8), abs=1e-9)
    assert fused_severity == pytest.approx(0.7059, abs=1e-3)


def test_low_reliability_modality_contributes_zero_weight_via_full_fuse_call():
    result = fuse_thermal_vibration_acoustic(
        _thermal(condition="Healthy", confidence=0.9),
        _vibration(prediction="degrading", confidence=0.8),
        _acoustic(accepted=False, prediction="uncertain", confidence=0.99, reliability="low"),  # suppressed despite high raw confidence
    )
    assert "acoustic" not in result["available_modalities"]
    assert result["reliability"] == "partial"
    expected = (0.9 * 0.0 + 0.8 * 0.5) / (0.9 + 0.8)
    assert result["fused_severity"] == pytest.approx(expected, abs=1e-4)
    # acoustic's raw confidence is still preserved in its own evidence block
    assert result["modality_evidence"]["acoustic"]["confidence"] == 0.99
    assert result["modality_evidence"]["acoustic"]["prediction"] is None


# --- missing / suppressed modality combinations -----------------------------

def test_missing_modality_none_argument():
    result = fuse_thermal_vibration_acoustic(_thermal(), _vibration(), None)
    assert result["modality_evidence"]["acoustic"]["available"] is False
    assert "acoustic" not in result["available_modalities"]
    assert result["reliability"] == "partial"


def test_thermal_only():
    result = fuse_thermal_vibration_acoustic(_thermal(condition="Healthy", confidence=0.91), None, None)
    assert result["available_modalities"] == ["thermal"]
    assert result["fused_severity"] == pytest.approx(0.0, abs=1e-9)
    assert result["fused_confidence"] == pytest.approx(0.91 / 3, abs=1e-4)
    assert result["reliability"] == "partial"


def test_vibration_only():
    result = fuse_thermal_vibration_acoustic(None, _vibration(prediction="severe", confidence=0.9), None)
    assert result["available_modalities"] == ["vibration"]
    assert result["fused_severity"] == pytest.approx(1.0, abs=1e-9)


def test_acoustic_only():
    result = fuse_thermal_vibration_acoustic(None, None, _acoustic(prediction="anomaly", confidence=0.9))
    assert result["available_modalities"] == ["acoustic"]
    assert result["fused_severity"] == pytest.approx(1.0, abs=1e-9)


def test_thermal_plus_vibration():
    result = fuse_thermal_vibration_acoustic(_thermal(condition="Healthy", confidence=0.9), _vibration(prediction="degrading", confidence=0.8), None)
    assert set(result["available_modalities"]) == {"thermal", "vibration"}
    assert result["reliability"] == "partial"


def test_thermal_plus_acoustic():
    result = fuse_thermal_vibration_acoustic(_thermal(condition="Healthy", confidence=0.9), None, _acoustic(prediction="normal", confidence=0.8))
    assert set(result["available_modalities"]) == {"thermal", "acoustic"}
    assert result["reliability"] == "partial"


def test_vibration_plus_acoustic():
    result = fuse_thermal_vibration_acoustic(None, _vibration(prediction="healthy", confidence=0.8), _acoustic(prediction="normal", confidence=0.8))
    assert set(result["available_modalities"]) == {"vibration", "acoustic"}
    assert result["reliability"] == "partial"


def test_thermal_suppressed_vibration_acoustic_available():
    result = fuse_thermal_vibration_acoustic(
        _thermal(prediction=None, condition=None, reliability="low"),
        _vibration(prediction="degrading", confidence=0.85),
        _acoustic(prediction="normal", confidence=0.85),
    )
    assert "thermal" not in result["available_modalities"]
    assert set(result["available_modalities"]) == {"vibration", "acoustic"}


def test_vibration_suppressed():
    result = fuse_thermal_vibration_acoustic(
        _thermal(condition="Healthy", confidence=0.85),
        _vibration(accepted=False, prediction="uncertain", confidence=0.6, reliability="low"),
        _acoustic(prediction="normal", confidence=0.85),
    )
    assert "vibration" not in result["available_modalities"]
    assert result["modality_evidence"]["vibration"]["prediction"] is None
    assert result["modality_evidence"]["vibration"]["confidence"] == 0.6  # preserved


def test_acoustic_suppressed_documented_scenario():
    result = fuse_thermal_vibration_acoustic(
        _thermal(condition="Corroded Bearing", confidence=0.88),
        _vibration(prediction="degrading", confidence=0.93),
        _acoustic(accepted=False, prediction="uncertain", confidence=0.67, reliability="low"),
    )
    assert "acoustic" not in result["available_modalities"]
    assert result["fused_severity"] == pytest.approx((0.88 * 1.0 + 0.93 * 0.5) / (0.88 + 0.93), abs=1e-4)


# --- zero-evidence scenario --------------------------------------------------

def test_zero_usable_modalities_never_fabricates_a_value():
    result = fuse_thermal_vibration_acoustic(None, None, None)
    assert result["fused_severity"] is None
    assert result["fused_confidence"] == 0.0
    assert result["reliability"] == "unavailable"
    assert result["available_modalities"] == []


def test_all_present_but_all_suppressed_is_also_unavailable():
    result = fuse_thermal_vibration_acoustic(
        _thermal(prediction=None, condition=None, reliability="low"),
        _vibration(accepted=False, prediction="uncertain", reliability="low"),
        _acoustic(accepted=False, prediction="uncertain", reliability="low"),
    )
    assert result["fused_severity"] is None
    assert result["reliability"] == "unavailable"


# --- malformed evidence -------------------------------------------------

def test_malformed_gate_result_missing_keys_does_not_crash():
    result = fuse_thermal_vibration_acoustic({}, {}, {})
    assert result["fused_severity"] is None
    assert result["reliability"] == "unavailable"


def test_accepted_but_unrecognized_class_raises_instead_of_guessing():
    bad_vibration = _vibration(accepted=True, prediction="catastrophic_meltdown", confidence=0.9, reliability="high")
    with pytest.raises(AmbiguousAnomalyStrengthMapping):
        fuse_thermal_vibration_acoustic(None, bad_vibration, None)


# --- deterministic output ----------------------------------------------

def test_deterministic_same_inputs_same_output():
    first = fuse_thermal_vibration_acoustic(_thermal(), _vibration(), _acoustic())
    second = fuse_thermal_vibration_acoustic(_thermal(), _vibration(), _acoustic())
    assert first == second


# --- telemetry serialization ---------------------------------------------

def test_result_is_json_serializable_and_matches_documented_shape():
    result = fuse_thermal_vibration_acoustic(_thermal(), _vibration(), _acoustic())
    dumped = json.dumps(result)  # must not raise
    reloaded = json.loads(dumped)
    for key in ("fused_severity", "fused_confidence", "reliability", "available_modalities", "model_type", "version"):
        assert key in reloaded


def test_telemetry_payload_accepts_ml_fusion_block():
    from datetime import datetime, timezone

    from app.models.schemas import TelemetryPayload

    result = fuse_thermal_vibration_acoustic(_thermal(), _vibration(), _acoustic())
    payload = TelemetryPayload(
        timestamp=datetime.now(timezone.utc),
        machine_id="m1",
        mode="demo",
        thermal=None,
        vibration=None,
        acoustic=None,
        health=None,
        ml_fusion=result,
        events=[],
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["ml_fusion"]["model_type"] == "weighted_evidence_fusion"
    assert dumped["ml_fusion"]["version"] == "fusion_v1"


def test_telemetry_payload_ml_fusion_defaults_to_none():
    from datetime import datetime, timezone

    from app.models.schemas import TelemetryPayload

    payload = TelemetryPayload(timestamp=datetime.now(timezone.utc), machine_id="m1", mode="demo")
    assert payload.model_dump(mode="json")["ml_fusion"] is None


# --- schema-mapping helper functions (build_*_evidence) ---------------------

def test_build_thermal_evidence_none_is_unavailable():
    ev = build_thermal_evidence(None)
    assert ev["available"] is False
    assert ev["reliability"] == "unavailable"
    assert "known_limitation" in ev and ev["known_limitation"]


def test_build_vibration_evidence_preserves_known_limitation():
    ev = build_vibration_evidence(_vibration())
    assert "derived-label" in ev["known_limitation"].lower()


def test_build_acoustic_evidence_preserves_known_limitation():
    ev = build_acoustic_evidence(_acoustic())
    assert "cross-section" in ev["known_limitation"].lower()


def test_build_thermal_evidence_preserves_condition_and_load_context():
    ev = build_thermal_evidence(_thermal(condition="Corroded Bearing", load="Medium"))
    assert ev["condition_context"] == "Corroded Bearing"
    assert ev["load_context"] == "Medium"
