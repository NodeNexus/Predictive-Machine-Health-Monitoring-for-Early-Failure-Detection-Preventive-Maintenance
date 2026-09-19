#!/usr/bin/env python
"""ACOUSTIC ML V1 CONFIDENCE GATE - step 6: prediction consistency across
section/domain groupings (NOT temporal smoothing - these are independently
recorded 10-second clips, not windows of one shared recording, so no
temporal-continuity behavior exists to smooth or check for oscillation).

Evaluates how the chosen confidence gate threshold (0.80) behaves within
each (section, domain) group on the test set - coverage and accepted-set
accuracy per group - to see whether the gate is roughly equally effective
everywhere or concentrates its rejections/errors in specific sections.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.acoustic.dataset import build_feature_matrix, load_split_manifest, records_for_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "models" / "acoustic"
THRESHOLD = 0.80


def main() -> None:
    manifest = load_split_manifest()
    test_records = records_for_split(manifest, "test")
    X_test, y_test, groups_test = build_feature_matrix(test_records)

    bundle = joblib.load(MODEL_DIR / "acoustic_baseline_v1.joblib")
    model = bundle["model"]
    scaler = bundle.get("scaler")
    X = scaler.transform(X_test) if scaler is not None else X_test

    probs_anomaly = model.predict_proba(X)[:, 1]
    preds = (probs_anomaly >= 0.5).astype(int)
    confidence = np.where(preds == 1, probs_anomaly, 1 - probs_anomaly)
    accepted_mask = confidence >= THRESHOLD

    result = {}
    for group in sorted(set(groups_test.tolist())):
        gmask = groups_test == group
        n = int(gmask.sum())
        n_accepted = int((gmask & accepted_mask).sum())
        coverage = n_accepted / n if n else None
        if n_accepted > 0:
            acc_mask = gmask & accepted_mask
            accuracy_on_accepted = float((preds[acc_mask] == y_test[acc_mask]).mean())
        else:
            accuracy_on_accepted = None
        result[group] = {
            "n": n,
            "n_accepted": n_accepted,
            "coverage": coverage,
            "accuracy_on_accepted": accuracy_on_accepted,
        }
        print(f"{group}: n={n} accepted={n_accepted} coverage={coverage} accuracy_on_accepted={accuracy_on_accepted}")

    out = {
        "threshold": THRESHOLD,
        "note": "These are independently recorded 10-second clips, not windows of a shared longer "
        "recording (unlike Vibration ML V1's IMS timeline) - there is no temporal-continuity behavior "
        "to check for oscillation, and no temporal smoothing was added since none is warranted.",
        "by_section_domain_group": result,
    }
    out_path = MODEL_DIR / "group_confidence_check.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
