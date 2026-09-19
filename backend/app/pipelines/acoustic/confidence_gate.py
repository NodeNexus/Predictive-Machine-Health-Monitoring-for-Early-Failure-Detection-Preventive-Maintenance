"""Gates a raw Acoustic ML V1 model prediction (see
models/acoustic/acoustic_baseline_v1.joblib and
models/acoustic/model_metadata.json) into a safe, evidence-only shape.

MODEL: Logistic Regression, binary (normal/anomaly). Unlike Vibration ML
V1, normal/anomaly here ARE the dataset's own native vendor-assigned
labels, not derived by this project - see model_metadata.json's
label_provenance_note.

CONFIDENCE ANALYSIS (models/acoustic/confidence_analysis.json, computed on
the untouched 537-sample test set): confidence here IS a genuinely useful
signal, unlike Vibration ML V1's tautological confidence - mean confidence
for correct predictions (0.959) is meaningfully higher than for incorrect
predictions (0.792), and calibration was actually measured (not assumed):
Brier score 0.036, Expected Calibration Error 0.017 (both low - "low" is
not "zero"; the lowest-confidence bin, 0.50-0.55, has an ECE gap of 0.13
on only 6 samples and should not be over-trusted).

ENGINEERING THRESHOLD = 0.80, chosen for a documented operational reason,
not to maximize a single metric: it is the LOWEST threshold at which
false negatives (missed real anomalies) drop to zero on the test set,
while keeping 91.8% coverage. In a predictive-maintenance context, a
missed anomaly (silent failure) is judged costlier than a false alarm
(an unnecessary inspection) or moderate prediction suppression - pushing
the threshold higher (e.g. 0.90, 0.95) buys additional anomaly precision
(0.825, 0.875) but FN was already zero at 0.80, so the extra suppression
(dropping coverage to 85.7%, then 77.7%) isn't bought with a matching
safety gain. See models/acoustic/confidence_analysis.json for the full
threshold sweep this was chosen from.

CRITICAL CROSS-SECTION LIMITATION (must never be lost - repeated here, not
only in the training report): test performance varies substantially by
recording section (models/acoustic/model_metadata.json's
robustness_by_section_domain_group: macro-F1 ranges 0.789-0.965 across
section|domain groups). A HIGH CONFIDENCE OUTPUT FROM THIS GATE IS NOT
PROOF OF CROSS-SECTION GENERALIZATION - it reflects the model's own
probability estimate on this clip, not a verified guarantee that the
model performs equally well on whatever machine/section produced it.
Confidence and proven generalization are two different things and must
never be conflated when this evidence is read downstream.

This module NEVER lets a raw ML class label stand in for a definitive
anomaly diagnosis. Low-confidence, malformed, or missing predictions
become "uncertain" rather than "anomaly"/"normal".
"""
from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.80
VALID_CLASSES = ("normal", "anomaly")


def apply_confidence_gate(
    prediction: dict | None,
    model_version: str | None = None,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> dict:
    """`prediction` is expected to look like
    {"predicted_class": "normal"|"anomaly", "confidence": float,
    "probabilities": {"normal": float, "anomaly": float} (optional),
    "model_version": str (optional)}, or None if the model was unavailable
    / inference failed for this clip.

    Always returns: accepted, prediction, confidence, reliability, reason.
    `prediction` in the return value is "uncertain" whenever `accepted` is
    False - a rejected prediction is never exposed as "anomaly" or
    "normal". A "high" reliability here means "confidence exceeded the
    engineering threshold on this clip" - it does NOT mean cross-section
    generalization has been verified (see module docstring).
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
        "reason": (
            f"confidence {confidence:.3f} >= threshold {threshold:.2f} "
            "(high LOCAL confidence only - cross-section generalization not verified, "
            "see model_metadata.json robustness_by_section_domain_group)"
        ),
        "model_version": version,
    }


def to_telemetry_fields(gate_result: dict) -> dict:
    """Maps a gate result to the WebSocket telemetry shape, nested under
    the existing "acoustic" block (so "ml_" is enough of a prefix there -
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
    """Maps a gate result to namespaced evidence field names, for use
    outside a nested "acoustic" telemetry block (mirrors
    app.pipelines.vibration.confidence_gate.to_evidence_fields). Not wired
    into demo_runner/fusion/WebSocket telemetry by this task."""
    return {
        "acoustic_ml_prediction": gate_result["prediction"],
        "acoustic_ml_confidence": gate_result["confidence"],
        "acoustic_ml_reliability": gate_result["reliability"],
        "acoustic_ml_model_version": gate_result["model_version"],
    }
