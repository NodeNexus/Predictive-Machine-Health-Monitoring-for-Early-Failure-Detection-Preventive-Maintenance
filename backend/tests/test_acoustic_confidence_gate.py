"""Tests for the Acoustic ML confidence gate
(app.pipelines.acoustic.confidence_gate). Pure unit tests against the gate
function only - no model loading, no live integration.
"""
from __future__ import annotations

from app.pipelines.acoustic.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    apply_confidence_gate,
    to_evidence_fields,
)


def test_high_confidence_normal_is_accepted():
    result = apply_confidence_gate({"predicted_class": "normal", "confidence": 0.97, "model_version": "acoustic-v1"})
    assert result["accepted"] is True
    assert result["prediction"] == "normal"
    assert result["confidence"] == 0.97
    assert result["reliability"] == "high"


def test_high_confidence_anomaly_is_accepted():
    result = apply_confidence_gate({"predicted_class": "anomaly", "confidence": 0.92, "model_version": "acoustic-v1"})
    assert result["accepted"] is True
    assert result["prediction"] == "anomaly"
    assert result["reliability"] == "high"


def test_low_confidence_prediction_is_suppressed_to_uncertain():
    result = apply_confidence_gate({"predicted_class": "anomaly", "confidence": 0.55, "model_version": "acoustic-v1"})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["confidence"] == 0.55  # raw confidence preserved even when suppressed
    assert result["reliability"] == "low"


def test_exact_threshold_is_accepted():
    result = apply_confidence_gate({"predicted_class": "normal", "confidence": CONFIDENCE_THRESHOLD})
    assert result["accepted"] is True


def test_just_below_threshold_is_rejected():
    result = apply_confidence_gate({"predicted_class": "normal", "confidence": CONFIDENCE_THRESHOLD - 1e-9})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"


def test_malformed_class_is_rejected():
    result = apply_confidence_gate({"predicted_class": "definitely_broken", "confidence": 0.99})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert "malformed" in result["reason"]


def test_missing_probability_is_rejected():
    result = apply_confidence_gate({"predicted_class": "anomaly"})
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert "missing" in result["reason"]


def test_none_prediction_is_rejected_as_unavailable():
    result = apply_confidence_gate(None, model_version="acoustic-v1")
    assert result["accepted"] is False
    assert result["prediction"] == "uncertain"
    assert result["reliability"] == "unavailable"
    assert result["model_version"] == "acoustic-v1"


def test_deterministic_behavior():
    payload = {"predicted_class": "anomaly", "confidence": 0.85, "model_version": "acoustic-v1"}
    first = apply_confidence_gate(dict(payload))
    second = apply_confidence_gate(dict(payload))
    assert first == second


def test_high_reliability_reason_flags_cross_section_caveat():
    """The gate must never imply proven cross-section generalization just
    because confidence cleared the threshold - see model_metadata.json's
    robustness_by_section_domain_group finding."""
    result = apply_confidence_gate({"predicted_class": "anomaly", "confidence": 0.95})
    assert result["reliability"] == "high"
    assert "cross-section" in result["reason"] or "generalization" in result["reason"]


def test_to_evidence_fields_shape():
    gate_result = apply_confidence_gate({"predicted_class": "anomaly", "confidence": 0.9, "model_version": "acoustic-v1"})
    evidence = to_evidence_fields(gate_result)
    assert evidence["acoustic_ml_prediction"] == "anomaly"
    assert evidence["acoustic_ml_confidence"] == 0.9
    assert evidence["acoustic_ml_reliability"] == "high"
    assert evidence["acoustic_ml_model_version"] == "acoustic-v1"


def test_never_exposes_a_class_label_when_rejected():
    for payload in (
        {"predicted_class": "anomaly", "confidence": 0.1},
        {"predicted_class": "bogus", "confidence": 0.99},
        {"predicted_class": "normal"},
        None,
    ):
        result = apply_confidence_gate(payload)
        if not result["accepted"]:
            assert result["prediction"] == "uncertain"
