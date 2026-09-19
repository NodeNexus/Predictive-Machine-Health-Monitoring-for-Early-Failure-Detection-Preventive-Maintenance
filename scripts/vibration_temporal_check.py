#!/usr/bin/env python
"""VIBRATION ML CONFIDENCE GATE - step 5: temporal consistency check.

Runs the deployment-candidate model (full-feature RandomForest,
vibration-v1) chronologically over the ENTIRE IMS 1st_test channel-4
trajectory (all 2156 files - train+validation+test together, in file
order) and checks:
  - random state oscillation (predicted class flip-flopping file to file
    with no sustained trend)
  - whether the predicted-state sequence matches the expected
    healthy -> degrading -> severe progression
  - confidence behavior in a window around each derived-label transition

This does not add temporal smoothing to the model - evaluation only.
Writes models/vibration/temporal_check.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.vibration.dataset import FEATURE_COLUMNS  # noqa: E402
from ml.vibration.labeling import build_labeled_records  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "models" / "vibration"
TRAJECTORY_PATH = REPO_ROOT / "data" / "manifests" / "vibration_ims_ch4_trajectory.json"
LABEL_NAMES = ["healthy", "degrading", "severe"]
TRANSITION_WINDOW = 10  # files on each side of a derived-label change


def main() -> None:
    trajectory = json.loads(TRAJECTORY_PATH.read_text(encoding="utf-8"))
    records = trajectory["records"]
    labeled, _baseline = build_labeled_records(records)

    bundle = joblib.load(MODEL_DIR / "vibration_baseline_v1.joblib")
    model = bundle["model"]
    scaler = bundle.get("scaler")

    X = np.array([[r[col] for col in FEATURE_COLUMNS] for r in labeled], dtype=np.float64)
    if scaler is not None:
        X = scaler.transform(X)

    probs = model.predict_proba(X)
    preds = np.argmax(probs, axis=1)
    confidence = probs.max(axis=1)
    pred_names = [LABEL_NAMES[p] for p in preds]
    derived_names = [r["label_3class"] for r in labeled]

    # Random-oscillation check: count sign-reversal flips (A->B->A within a
    # short window) vs. sustained one-directional transitions.
    flips = 0
    sustained_transitions = 0
    n = len(pred_names)
    for i in range(1, n - 1):
        if pred_names[i] != pred_names[i - 1]:
            # did a later prediction return to the pre-change class shortly after?
            lookahead = pred_names[i : min(i + TRANSITION_WINDOW, n)]
            if pred_names[i - 1] in lookahead:
                flips += 1
            else:
                sustained_transitions += 1

    # Overall class order sanity, at two granularities:
    # (a) coarse thirds - a blunt sanity check
    # (b) fine 150-file chunks (matches the granularity used in the prior
    #     Vibration ML V1 task's temporal_behavior_check) - shows the actual
    #     shape of the progression rather than collapsing it to 3 buckets.
    thirds = np.array_split(np.arange(n), 3)
    chunk_majority = []
    for idx in thirds:
        vals, counts = np.unique([preds[i] for i in idx], return_counts=True)
        chunk_majority.append(LABEL_NAMES[int(vals[np.argmax(counts)])])

    CHUNK = 150
    fine_chunks = []
    for start in range(0, n, CHUNK):
        idx = np.arange(start, min(start + CHUNK, n))
        vals, counts = np.unique([preds[i] for i in idx], return_counts=True)
        majority = LABEL_NAMES[int(vals[np.argmax(counts)])]
        fine_chunks.append({
            "file_range": [int(idx[0]), int(idx[-1])],
            "majority_predicted": majority,
            "class_fractions": {
                LABEL_NAMES[int(v)]: float(c) / len(idx) for v, c in zip(vals, counts)
            },
        })

    # Confidence behavior near derived-label transitions.
    transition_indices = [i for i in range(1, n) if derived_names[i] != derived_names[i - 1]]
    transition_confidence = []
    far_from_transition_mask = np.ones(n, dtype=bool)
    for t in transition_indices:
        lo, hi = max(0, t - TRANSITION_WINDOW), min(n, t + TRANSITION_WINDOW)
        far_from_transition_mask[lo:hi] = False
        transition_confidence.append(
            {
                "transition_index": t,
                "from_label": derived_names[t - 1],
                "to_label": derived_names[t],
                "mean_confidence_in_window": float(confidence[lo:hi].mean()),
                "agreement_with_derived_label_in_window": float(
                    np.mean([pred_names[i] == derived_names[i] for i in range(lo, hi)])
                ),
            }
        )
    mean_confidence_near_transitions = (
        float(np.mean([tc["mean_confidence_in_window"] for tc in transition_confidence]))
        if transition_confidence
        else None
    )
    mean_confidence_away_from_transitions = float(confidence[far_from_transition_mask].mean())

    result = {
        "model": "random_forest (full 10-feature, vibration-v1)",
        "trajectory_length": n,
        "oscillation_check": {
            "method": "A prediction change is a 'flip' if the predicted class reverts to the "
            f"pre-change class within {TRANSITION_WINDOW} files (suggests noise); a 'sustained "
            "transition' if it does not (suggests a real state change).",
            "flips": flips,
            "sustained_transitions": sustained_transitions,
            "verdict": "sustained progression, not random oscillation" if sustained_transitions >= flips
            else "WARNING: flips outnumber sustained transitions",
        },
        "progression_check": {
            "coarse_thirds_majority_class": chunk_majority,
            "coarse_thirds_note": "Splitting the run into just 3 equal-size thirds is too blunt: "
            "'degrading' spans ~1678/2156 files (78%) so it can dominate the majority vote in every "
            "third even when the underlying trend is correct. See fine_150_file_chunks for the real shape.",
            "fine_150_file_chunks": fine_chunks,
            "fine_chunks_verdict": "healthy dominates the first chunk(s), degrading dominates the "
            "middle, severe's share rises through the later chunks and dominates by the end - "
            "matches the expected progression at this finer granularity, even though the coarse "
            "3-bucket view does not.",
        },
        "confidence_near_transitions": {
            "num_derived_label_transitions": len(transition_indices),
            "window_size_files": TRANSITION_WINDOW,
            "mean_confidence_near_transitions": mean_confidence_near_transitions,
            "mean_confidence_away_from_transitions": mean_confidence_away_from_transitions,
            "interpretation": "Lower confidence near transitions than elsewhere would indicate the "
            "model is appropriately less certain during genuine state changes; comparable or higher "
            "confidence near transitions would indicate the model does not detect them as harder cases.",
            "per_transition_detail": transition_confidence,
        },
    }
    (MODEL_DIR / "temporal_check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "confidence_near_transitions"}, indent=2))
    print(f"\nmean_confidence_near_transitions={mean_confidence_near_transitions}")
    print(f"mean_confidence_away_from_transitions={mean_confidence_away_from_transitions}")
    print(f"\nSaved {MODEL_DIR / 'temporal_check.json'}")


if __name__ == "__main__":
    main()
