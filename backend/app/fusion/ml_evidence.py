"""Multimodal ML Evidence Fusion V1 - weighted evidence-level fusion of the
three independently trained, independently confidence-gated modality ML
models (thermal, vibration, acoustic).

This is NOT a trained fusion model and does NOT require synchronized
multimodal training data - see models/fusion/fusion_task_definition.json
for why no such dataset exists and why evidence-level fusion (Candidate 2:
weighted evidence fusion) was selected instead of a supervised classifier.
The exact formula implemented here was validated offline in
scripts/fusion_evidence_fusion_demo.py against
models/fusion/fusion_evidence_schema.json's worked examples BEFORE this
module was written.

This module is pure and deterministic: given the same three raw
confidence-gate outputs, it always returns the same result. It has no
dependency on the dashboard, the WebSocket hub, or raw sensor processing -
it consumes only the ALREADY-PRODUCED per-modality ML evidence (each
modality's own apply_confidence_gate() output), never re-running or
duplicating any modality's inference.

CRITICAL: app.fusion.engine.FusionEngine (the existing deterministic
health/anomaly/event engine) is completely untouched by this module and
remains authoritative for health_score/status/severity/events. This
module's output is ADDITIONAL evidence, never a replacement.
"""
from __future__ import annotations

MODEL_TYPE = "weighted_evidence_fusion"
VERSION = "fusion_v1"

# Fixed, non-editable-at-runtime limitation strings - carried forward from
# each modality's own V1 task so fusion output can never be read as if the
# underlying models were more validated than they actually are. Verbatim
# from models/fusion/fusion_evidence_schema.json.
KNOWN_LIMITATIONS = {
    "thermal": (
        "Load-level confusion is significant (CFL<->CML, HML->HFL); confidence does not reliably "
        "separate this specific error mode (median confidence nearly identical for correct vs incorrect "
        "predictions)."
    ),
    "vibration": (
        "Labels are project-derived from the IMS degradation trajectory via a documented statistical "
        "rule, not original dataset ground truth. RMS and kurtosis participate in both the input "
        "features and the label-construction rule. This is a derived-label trajectory classifier, NOT "
        "an independently validated fault detector."
    ),
    "acoustic": (
        "High LOCAL confidence only - cross-section generalization not verified (macro-F1 ranges "
        "0.789-0.965 across section|domain groups on the test set)."
    ),
}

# Exact mappings from models/fusion/fusion_evidence_schema.json's
# modality_specific_extension_fields.*.anomaly_strength_mapping - reused
# verbatim, not reinvented. Any class not listed here (there are none
# currently) would be genuinely ambiguous and must NOT be silently mapped -
# see _map_class_to_strength.
_THERMAL_CONDITION_TO_STRENGTH = {"Healthy": 0.0, "Corroded Bearing": 1.0}
_VIBRATION_CLASS_TO_STRENGTH = {"healthy": 0.0, "degrading": 0.5, "severe": 1.0}
_ACOUSTIC_CLASS_TO_STRENGTH = {"normal": 0.0, "anomaly": 1.0}

MODALITIES = ("thermal", "vibration", "acoustic")


class AmbiguousAnomalyStrengthMapping(ValueError):
    """Raised when a modality reports a class this module has no documented
    anomaly_strength mapping for - per this task's explicit instruction to
    stop and report rather than inventing a mapping."""


def _map_class_to_strength(modality: str, value: str | None, mapping: dict[str, float]) -> float | None:
    if value is None:
        return None
    if value not in mapping:
        raise AmbiguousAnomalyStrengthMapping(
            f"{modality} class {value!r} has no documented anomaly_strength mapping in "
            "models/fusion/fusion_evidence_schema.json - refusing to invent one."
        )
    return mapping[value]


def build_thermal_evidence(gate_result: dict | None) -> dict:
    """`gate_result` is the raw output of
    app.pipelines.thermal.confidence_gate.apply_confidence_gate(), or None
    if thermal was not part of this session at all."""
    if gate_result is None:
        return {
            "available": False,
            "prediction": None,
            "confidence": None,
            "reliability": "unavailable",
            "anomaly_strength": None,
            "condition_context": None,
            "load_context": None,
            "model_version": None,
            "known_limitation": KNOWN_LIMITATIONS["thermal"],
        }
    predicted = gate_result.get("ml_prediction")
    condition = gate_result.get("ml_condition")
    # Only map a class to a severity when the gate actually asserted a
    # prediction (predicted is not None); a suppressed/unavailable reading
    # carries no class to map, so anomaly_strength is None, not looked up.
    anomaly_strength = _map_class_to_strength("thermal", condition, _THERMAL_CONDITION_TO_STRENGTH) if predicted is not None else None
    return {
        "available": True,
        "prediction": predicted,
        "confidence": gate_result.get("ml_confidence"),
        "reliability": gate_result.get("ml_reliability", "unavailable"),
        "anomaly_strength": anomaly_strength,
        "condition_context": condition,
        "load_context": gate_result.get("ml_load_context"),
        "model_version": gate_result.get("model_version"),
        "known_limitation": KNOWN_LIMITATIONS["thermal"],
    }


def build_vibration_evidence(gate_result: dict | None) -> dict:
    """`gate_result` is the raw output of
    app.pipelines.vibration.confidence_gate.apply_confidence_gate(), or
    None if vibration was not part of this session at all."""
    if gate_result is None:
        return {
            "available": False,
            "prediction": None,
            "confidence": None,
            "reliability": "unavailable",
            "anomaly_strength": None,
            "model_version": None,
            "known_limitation": KNOWN_LIMITATIONS["vibration"],
        }
    accepted = bool(gate_result.get("accepted"))
    raw_prediction = gate_result.get("prediction")
    # "uncertain" (the gate's own suppressed-prediction literal) is never
    # mapped - only an ACCEPTED prediction's class is looked up, and an
    # accepted-but-unrecognized class raises rather than being silently
    # treated as "no evidence" (see _map_class_to_strength).
    anomaly_strength = _map_class_to_strength("vibration", raw_prediction, _VIBRATION_CLASS_TO_STRENGTH) if accepted else None
    return {
        "available": True,
        "prediction": raw_prediction if accepted else None,
        "confidence": gate_result.get("confidence"),
        "reliability": gate_result.get("reliability", "unavailable"),
        "anomaly_strength": anomaly_strength,
        "model_version": gate_result.get("model_version"),
        "known_limitation": KNOWN_LIMITATIONS["vibration"],
    }


def build_acoustic_evidence(gate_result: dict | None) -> dict:
    """`gate_result` is the raw output of
    app.pipelines.acoustic.confidence_gate.apply_confidence_gate(), or
    None if acoustic was not part of this session at all."""
    if gate_result is None:
        return {
            "available": False,
            "prediction": None,
            "confidence": None,
            "reliability": "unavailable",
            "anomaly_strength": None,
            "model_version": None,
            "known_limitation": KNOWN_LIMITATIONS["acoustic"],
        }
    accepted = bool(gate_result.get("accepted"))
    raw_prediction = gate_result.get("prediction")
    anomaly_strength = _map_class_to_strength("acoustic", raw_prediction, _ACOUSTIC_CLASS_TO_STRENGTH) if accepted else None
    return {
        "available": True,
        "prediction": raw_prediction if accepted else None,
        "confidence": gate_result.get("confidence"),
        "reliability": gate_result.get("reliability", "unavailable"),
        "anomaly_strength": anomaly_strength,
        "model_version": gate_result.get("model_version"),
        "known_limitation": KNOWN_LIMITATIONS["acoustic"],
    }


def _weight(evidence: dict) -> float:
    """weight_m = confidence_m if reliability_m == 'high' else 0 - a
    suppressed ('low') or unavailable modality NEVER contributes weight,
    regardless of its raw confidence value."""
    if evidence.get("reliability") == "high" and evidence.get("confidence") is not None and evidence.get("anomaly_strength") is not None:
        return float(evidence["confidence"])
    return 0.0


def fuse_thermal_vibration_acoustic(
    thermal_evidence: dict | None,
    vibration_evidence: dict | None,
    acoustic_evidence: dict | None,
) -> dict:
    """Consumes the three modalities' RAW confidence-gate outputs (not
    re-derived, not re-inferred) and returns the ml_fusion telemetry block.

    Each `*_evidence` argument is the raw dict returned by that modality's
    own apply_confidence_gate() (see build_thermal_evidence /
    build_vibration_evidence / build_acoustic_evidence for the exact
    expected shape), or None if that modality was not part of this session.

    Deterministic and pure: same inputs always produce the same output.
    Raises AmbiguousAnomalyStrengthMapping if a modality reports a class
    with no documented mapping - this is intentional; it must surface as an
    error rather than silently guessing a severity.
    """
    thermal = build_thermal_evidence(thermal_evidence)
    vibration = build_vibration_evidence(vibration_evidence)
    acoustic = build_acoustic_evidence(acoustic_evidence)
    modality_evidence = {"thermal": thermal, "vibration": vibration, "acoustic": acoustic}

    weights = {name: _weight(ev) for name, ev in modality_evidence.items()}
    total_weight = sum(weights.values())
    available_modalities = [name for name in MODALITIES if weights[name] > 0]

    if total_weight > 0:
        fused_severity = sum(
            weights[name] * modality_evidence[name]["anomaly_strength"] for name in available_modalities
        ) / total_weight
        fused_severity = round(fused_severity, 4)
    else:
        fused_severity = None  # never silently substitute zero for missing evidence

    fused_confidence = round(total_weight / len(MODALITIES), 4)

    if len(available_modalities) == 0:
        reliability = "unavailable"
    elif len(available_modalities) < len(MODALITIES):
        reliability = "partial"
    else:
        reliability = "high"

    return {
        "fused_severity": fused_severity,
        "fused_confidence": fused_confidence,
        "reliability": reliability,
        "available_modalities": available_modalities,
        "model_type": MODEL_TYPE,
        "version": VERSION,
        "modality_evidence": modality_evidence,
    }
