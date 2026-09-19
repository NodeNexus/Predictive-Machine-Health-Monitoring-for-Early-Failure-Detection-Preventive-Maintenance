#!/usr/bin/env python
"""MULTIMODAL FUSION V1 - offline sanity check for the weighted evidence
fusion formula defined in models/fusion/fusion_architecture_design.md.

This is a DESIGN-VALIDATION script only: it does not import, call, or
modify any production runtime code (demo_runner, app/fusion/engine.py,
telemetry, dashboard). It reimplements the documented formula standalone
and runs it against the four scenarios from
models/fusion/fusion_evidence_schema.json's worked_examples, to confirm
the formula behaves as documented (correct weighting, correct handling of
suppressed/missing modalities, never fabricating a value) before any
future implementation task builds on it.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "models" / "fusion" / "fusion_evidence_schema.json"
MODALITIES = ("thermal_evidence", "vibration_evidence", "acoustic_evidence")


def fuse(evidence: dict) -> dict:
    """Implements fusion_architecture_design.md section 4 exactly:
    weight_m = confidence_m if reliability_m == "high" else 0
    fused_severity = weighted average of anomaly_strength over weight>0, else None
    fused_confidence = sum(weights) / 3
    """
    weights = {}
    strengths = {}
    for key in MODALITIES:
        block = evidence[key]
        if block.get("reliability") == "high" and block.get("confidence") is not None:
            weights[key] = block["confidence"]
            strengths[key] = block["anomaly_strength"]
        else:
            weights[key] = 0.0
            strengths[key] = block.get("anomaly_strength")

    total_weight = sum(weights.values())
    if total_weight > 0:
        fused_severity = sum(weights[k] * strengths[k] for k in MODALITIES if weights[k] > 0) / total_weight
        reliability = "computed"
    else:
        fused_severity = None
        reliability = "unavailable"

    fused_confidence = total_weight / len(MODALITIES)

    return {
        "weights": weights,
        "fused_severity": fused_severity,
        "fused_confidence": round(fused_confidence, 4),
        "fused_reliability": reliability,
    }


def main() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    examples = schema["worked_examples"]

    for name, evidence in examples.items():
        result = fuse(evidence)
        print(f"\n=== {name} ===")
        for key in MODALITIES:
            b = evidence[key]
            print(f"  {key}: available={b['available']} prediction={b['prediction']} "
                  f"confidence={b['confidence']} reliability={b['reliability']} anomaly_strength={b['anomaly_strength']}")
        print(f"  -> weights={result['weights']}")
        print(f"  -> fused_severity={result['fused_severity']} fused_confidence={result['fused_confidence']} "
              f"fused_reliability={result['fused_reliability']}")

    # Explicit assertions confirming the documented behavior, not just printed output.
    mixed = fuse(examples["high_confidence_all_three_mixed_severity"])
    assert mixed["fused_severity"] is not None and 0.0 < mixed["fused_severity"] < 1.0

    suppressed = fuse(examples["acoustic_suppressed"])
    assert suppressed["weights"]["acoustic_evidence"] == 0.0, "suppressed modality must contribute zero weight"
    assert suppressed["fused_severity"] is not None  # thermal+vibration still available

    thermal_only = fuse(examples["thermal_only"])
    assert thermal_only["weights"]["vibration_evidence"] == 0.0
    assert thermal_only["weights"]["acoustic_evidence"] == 0.0
    assert abs(thermal_only["fused_confidence"] - (0.91 / 3)) < 1e-3  # fused_confidence is rounded to 4dp

    unavailable = fuse(examples["all_unavailable"])
    assert unavailable["fused_severity"] is None, "must never fabricate a value with zero evidence"
    assert unavailable["fused_reliability"] == "unavailable"

    print("\nAll documented behaviors confirmed: suppressed/absent modalities contribute zero weight, "
          "fusion never fabricates a value with no evidence, confidence scales with coverage.")


if __name__ == "__main__":
    main()
