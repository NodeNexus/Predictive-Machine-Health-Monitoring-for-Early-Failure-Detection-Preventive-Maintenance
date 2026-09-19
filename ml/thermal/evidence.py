"""Converts a raw ThermalClassifier prediction into machine-health evidence,
without inventing any severity or condition the dataset doesn't support.

The Dataset-1 labels directly encode two independent axes:
  - condition: Healthy (H) vs. Corroded Bearing (C)
  - operating_context: Full/Medium/No Load (FL/ML/NL)

Nothing beyond that is claimed. In particular this module never emits
"critical", "unsafe", or a machine-will-fail style statement - the dataset
has no severity axis at all, only a binary condition label.
"""
from __future__ import annotations

_CONDITION_TYPE = {
    "HFL": "healthy",
    "HML": "healthy",
    "HNL": "healthy",
    "CFL": "bearing_fault_indication",
    "CML": "bearing_fault_indication",
    "CNL": "bearing_fault_indication",
}

_OPERATING_CONTEXT = {
    "HFL": "full_load",
    "CFL": "full_load",
    "HML": "medium_load",
    "CML": "medium_load",
    "HNL": "no_load",
    "CNL": "no_load",
}


def to_health_evidence(prediction: dict) -> dict:
    """`prediction` is the dict returned by ThermalClassifier.predict()."""
    predicted_class = prediction["predicted_class"]
    return {
        "predicted_condition": predicted_class,
        "confidence": prediction["confidence"],
        "condition_type": _CONDITION_TYPE.get(predicted_class, "unknown"),
        "operating_context": _OPERATING_CONTEXT.get(predicted_class, "unknown"),
        "model_version": prediction.get("model_version"),
        "top_predictions": prediction.get("top_predictions", []),
    }
