"""Gates a raw ThermalMLModel prediction into the telemetry-facing evidence
shape, suppressing the predicted class/condition/load-context when
confidence is too low - while always preserving the raw confidence value
(even when suppressed) so the dashboard can show "the model saw something
but wasn't sure" rather than nothing at all.

IMPORTANT, measured finding (not a threshold-solves-everything claim):
on the real held-out test set, misclassified predictions have a MEDIAN
confidence of 0.962 - very slightly HIGHER than correct predictions'
median of 0.960. This model is frequently confidently wrong on the
specific load-level confusion documented in the training report (CFL<->CML,
HML->HFL); no confidence threshold reliably separates those wrong
predictions from correct ones. THRESHOLD = 0.6 was chosen only to reject
genuinely near-chance predictions (comparable to random guessing among 6
classes, ~0.167) - it is a floor against low-information output, not a
correctness filter for the model's known confusion mode. This is stated
here, in the module the dashboard depends on, rather than only in a
report, so the limitation isn't lost.
"""
from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.6

_CONDITION = {
    "HFL": "Healthy", "HML": "Healthy", "HNL": "Healthy",
    "CFL": "Corroded Bearing", "CML": "Corroded Bearing", "CNL": "Corroded Bearing",
}

_LOAD_CONTEXT = {
    "HFL": "Full", "CFL": "Full",
    "HML": "Medium", "CML": "Medium",
    "HNL": "No Load", "CNL": "No Load",
}


def apply_confidence_gate(prediction: dict | None, model_version: str | None, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """`prediction` is ThermalMLModel.predict()'s return value, or None if
    the model was unavailable / inference failed for this frame."""
    if prediction is None:
        return {
            "ml_prediction": None,
            "ml_confidence": None,
            "ml_condition": None,
            "ml_load_context": None,
            "ml_reliability": "unavailable",
            "model_version": model_version,
        }

    predicted_class = prediction["predicted_class"]
    confidence = prediction["confidence"]

    if confidence < threshold:
        return {
            "ml_prediction": None,
            "ml_confidence": confidence,
            "ml_condition": None,
            "ml_load_context": None,
            "ml_reliability": "low",
            "model_version": prediction.get("model_version", model_version),
        }

    return {
        "ml_prediction": predicted_class,
        "ml_confidence": confidence,
        "ml_condition": _CONDITION.get(predicted_class),
        "ml_load_context": _LOAD_CONTEXT.get(predicted_class),
        "ml_reliability": "high",
        "model_version": prediction.get("model_version", model_version),
    }
