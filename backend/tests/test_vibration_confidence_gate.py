"""Tests for the Vibration ML confidence gate
(app.pipelines.vibration.confidence_gate). Pure unit tests against the gate
function only - no model loading, no live integration.
"""
from __future__ import annotations

from app.pipelines.vibration.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    apply_confidence_gate,
    to_evidence_fields,
)


def test_accepted_high_confidence_prediction():
    result = apply_confidence_gate({"predicted_class": "degrading", "confidence": 0.95, "model_version": "v1"})
    assert result["accepted"] is True
    assert result["prediction"] == "degrading"
    assert result["confidence"] == 0.95
    assert result["reliability"] == "high"
    assert result["model_version"] == "v1"


def test_rejected_low_confidence_prediction_becomes_uncertain():
    result = apply_confidence_gate({"predicted_class": "severe", "confidence": 0.4, "model_version": "v1"})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["confidence"] == 0.4
    assert result["reliability"] == "low"
    assert "below threshold" in result["reason"]


def test_exact_threshold_is_accepted():
    result = apply_confidence_gate({"predicted_class": "healthy", "confidence": CONFIDENCE_THRESHOLD})
    assert result["accepted"] is True
    assert result["prediction"] == "healthy"


def test_just_below_threshold_is_rejected():
    result = apply_confidence_gate({"predicted_class": "healthy", "confidence": CONFIDENCE_THRESHOLD - 1e-9})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"


def test_all_three_classes_accepted_when_confident():
    for cls in ("healthy", "degrading", "severe"):
        result = apply_confidence_gate({"predicted_class": cls, "confidence": 0.99})
        assert result["accepted"] is True
        assert result["prediction"] == cls


def test_malformed_class_is_rejected():
    result = apply_confidence_gate({"predicted_class": "definitely_broken", "confidence": 0.99})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert "malformed" in result["reason"]


def test_missing_probability_is_rejected():
    result = apply_confidence_gate({"predicted_class": "healthy"})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert "missing" in result["reason"]


def test_none_prediction_is_rejected_as_unavailable():
    result = apply_confidence_gate(None, model_version="v1")
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert result["model_version"] == "v1"


def test_deterministic_behavior():
    payload = {"predicted_class": "degrading", "confidence": 0.93, "model_version": "vibration-v1"}
    first = apply_confidence_gate(dict(payload))
    second = apply_confidence_gate(dict(payload))
    assert first == second


def test_to_evidence_fields_shape():
    gate_result = apply_confidence_gate({"predicted_class": "severe", "confidence": 0.97, "model_version": "vibration-v1"})
    evidence = to_evidence_fields(gate_result)
    assert evidence == {
        "vibration_ml_prediction": "severe",
        "vibration_ml_confidence": 0.97,
        "vibration_ml_reliability": "high",
        "vibration_ml_model_version": "vibration-v1",
    }


def test_never_exposes_a_class_label_when_rejected():
    for payload in (
        {"predicted_class": "severe", "confidence": 0.1},
        {"predicted_class": "bogus", "confidence": 0.99},
        {"predicted_class": "healthy"},
        None,
    ):
        result = apply_confidence_gate(payload)
        if not result["accepted"]:
            assert result["prediction"] == "uncertain"
