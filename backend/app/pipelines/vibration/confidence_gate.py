"""Gates a raw Vibration ML V1 model prediction (see
models/vibration/vibration_baseline_v1.joblib and
models/vibration/vibration_task_definition.json) into a safe,
evidence-only shape for the IDEA LAB runtime.

CRITICAL LABEL-DEPENDENCY LIMITATION (must never be lost - repeated here,
not only in the training report): the underlying model's classes
(healthy / degrading / severe) are DERIVED labels, not original dataset
ground truth (the IMS run-to-failure dataset provides none). Two of the
model's own input features - rms and kurtosis - are also the exact
quantities the labels were computed from. This means a "confident" or
"correct" prediction on the held-out test set partly reflects the model
recovering its own labeling rule, not independently validated certainty
about real bearing health. See models/vibration/model_metadata.json's
IMPORTANT_tautology_finding before treating this model's output as
anything more than "a fast, queryable implementation of the documented
derived-labeling rule."

CONFIDENCE THRESHOLD, measured finding (not a correctness-filter claim):
on the real held-out test set (336 samples), the model made ZERO
misclassifications at any confidence level, so no threshold can be
validated against actual errors there - see
models/vibration/confidence_analysis.json. Across the full 2156-file
trajectory, confidence stays high (>=0.95) almost everywhere, including
right at derived-label transition boundaries (mean confidence near
transitions 0.986 vs. 0.998 away from transitions - only a marginal dip -
see models/vibration/temporal_check.json). THRESHOLD = 0.90 was chosen as
an engineering floor that rejects the minority of genuinely uncertain
per-file predictions (~5% of the test set falls below it) without
discarding most output - it is NOT evidence that predictions above this
threshold are independently validated as correct.

This module NEVER lets a raw ML class label stand in for machine health.
Low-confidence, malformed, or missing predictions become "uncertain"
rather than a definitive health state, and callers should treat all
output here as `vibration_ml_*` EVIDENCE alongside the deterministic
anomaly/fusion engine - not a replacement for it.
"""
from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.90
VALID_CLASSES = ("healthy", "degrading", "severe")


def apply_confidence_gate(
    prediction: dict | None,
    model_version: str | None = None,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> dict:
    """`prediction` is expected to look like
    {"predicted_class": "healthy"|"degrading"|"severe", "confidence": float,
    "model_version": str (optional)}, or None if the model was unavailable
    / inference failed for this sample.

    Always returns: accepted, prediction, confidence, reliability, reason.
    `prediction` in the return value is "uncertain" whenever `accepted` is
    False - a rejected prediction is never exposed as one of the three
    health classes.
    """
    if prediction is None:
        return {
            "accepted": False,
            "prediction": "uncertain",
            "confidence": None,
            "reliability": "unavailable",
            "reason": "no prediction available (model unavailable or inference failed)",
            "model_version": model_version,
        }

    predicted_class = prediction.get("predicted_class")
    confidence = prediction.get("confidence")
    version = prediction.get("model_version", model_version)

    if predicted_class not in VALID_CLASSES:
        return {
            "accepted": False,
            "prediction": "uncertain",
            "confidence": confidence,
            "reliability": "unavailable",
            "reason": f"malformed predicted_class: {predicted_class!r}",
            "model_version": version,
        }

    if confidence is None:
        return {
            "accepted": False,
            "prediction": "uncertain",
            "confidence": None,
            "reliability": "unavailable",
            "reason": "missing confidence/probability value",
            "model_version": version,
        }

    if confidence < threshold:
        return {
            "accepted": False,
            "prediction": "uncertain",
            "confidence": confidence,
            "reliability": "low",
            "reason": f"confidence {confidence:.3f} below threshold {threshold:.2f}",
            "model_version": version,
        }

    return {
        "accepted": True,
        "prediction": predicted_class,
        "confidence": confidence,
        "reliability": "high",
        "reason": f"confidence {confidence:.3f} >= threshold {threshold:.2f}",
        "model_version": version,
    }


def to_telemetry_fields(gate_result: dict) -> dict:
    """Maps a gate result to the WebSocket telemetry shape, nested under the
    existing "vibration" block (so "ml_" is enough of a prefix there -
    unlike `to_evidence_fields`, which is namespaced for use outside that
    block). Rejected/uncertain predictions surface as `ml_prediction: None`
    (never the literal "uncertain" string) so a raw None reads unambiguously
    as "no class asserted" to any downstream JSON consumer, while the raw
    confidence is still preserved even when suppressed."""
    return {
        "ml_prediction": gate_result["prediction"] if gate_result["accepted"] else None,
        "ml_confidence": gate_result["confidence"],
        "ml_reliability": gate_result["reliability"],
        "ml_model_version": gate_result["model_version"],
    }


def to_evidence_fields(gate_result: dict) -> dict:
    """Maps a gate result to the telemetry-facing evidence field names.

    These are named `vibration_ml_*` deliberately, to make clear this is
    ADDITIONAL EVIDENCE alongside the existing deterministic
    anomaly/fusion engine - never a value that replaces or overrides it.
    Not wired into demo_runner/fusion/WebSocket telemetry by this task;
    this only defines the shape for a future, separate integration step.
    """
    return {
        "vibration_ml_prediction": gate_result["prediction"],
        "vibration_ml_confidence": gate_result["confidence"],
        "vibration_ml_reliability": gate_result["reliability"],
        "vibration_ml_model_version": gate_result["model_version"],
    }
