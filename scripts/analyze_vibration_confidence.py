#!/usr/bin/env python
"""VIBRATION ML CONFIDENCE GATE - step 2: probability/threshold analysis.

Evaluates the deployment candidate model's (RandomForest, full 10-feature
set - see models/vibration/vibration_task_definition.json's deployment
rationale) predict_proba output on the UNTOUCHED test split, for several
candidate acceptance thresholds. This is a coverage/accuracy-under-rejection
study, NOT a calibration analysis (no reliability-diagram / Brier-score /
isotonic-regression work was performed, so calibration is never claimed).

Writes models/vibration/confidence_analysis.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import confusion_matrix, f1_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.vibration.dataset import build_feature_matrix, load_split_manifest, records_for_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "models" / "vibration"
LABEL_NAMES = ["healthy", "degrading", "severe"]
THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]


def main() -> None:
    manifest = load_split_manifest()
    test_records = [{**r, **r["features"]} for r in records_for_split(manifest, "test")]
    X_test, y_test, _ = build_feature_matrix(test_records)

    bundle = joblib.load(MODEL_DIR / "vibration_baseline_v1.joblib")
    model = bundle["model"]
    scaler = bundle.get("scaler")
    X = scaler.transform(X_test) if scaler is not None else X_test

    probs = model.predict_proba(X)
    preds = np.argmax(probs, axis=1)
    confidence = probs.max(axis=1)

    correct = preds == y_test

    # Confidence-vs-correctness association (not a formal calibration study).
    mean_conf_correct = float(confidence[correct].mean()) if correct.any() else None
    mean_conf_incorrect = float(confidence[~correct].mean()) if (~correct).any() else None
    median_conf_correct = float(np.median(confidence[correct])) if correct.any() else None
    median_conf_incorrect = float(np.median(confidence[~correct])) if (~correct).any() else None

    threshold_results = []
    for t in THRESHOLDS:
        accepted_mask = confidence >= t
        n_accepted = int(accepted_mask.sum())
        n_rejected = int((~accepted_mask).sum())
        entry = {
            "threshold": t,
            "coverage": n_accepted / len(y_test),
            "accepted_predictions": n_accepted,
            "rejected_predictions": n_rejected,
        }
        if n_accepted > 0:
            y_acc = y_test[accepted_mask]
            p_acc = preds[accepted_mask]
            entry["accuracy_on_accepted"] = float((y_acc == p_acc).mean())
            entry["macro_f1_on_accepted"] = float(f1_score(y_acc, p_acc, average="macro", zero_division=0))
            present_labels = sorted(set(y_acc.tolist()))
            recalls = recall_score(y_acc, p_acc, labels=present_labels, average=None, zero_division=0)
            entry["per_class_recall_on_accepted"] = {
                LABEL_NAMES[label]: float(r) for label, r in zip(present_labels, recalls)
            }
            entry["confusion_matrix_on_accepted"] = confusion_matrix(
                y_acc, p_acc, labels=list(range(len(LABEL_NAMES)))
            ).tolist()
        else:
            entry["accuracy_on_accepted"] = None
            entry["macro_f1_on_accepted"] = None
            entry["per_class_recall_on_accepted"] = {}
            entry["confusion_matrix_on_accepted"] = None
        threshold_results.append(entry)
        print(
            f"t={t:.2f} coverage={entry['coverage']:.3f} "
            f"acc={entry['accuracy_on_accepted']} macro_f1={entry['macro_f1_on_accepted']}"
        )

    result = {
        "model": "random_forest (full 10-feature, vibration-v1)",
        "note": "This is a coverage/accuracy-under-rejection sweep on the held-out test set, "
        "NOT a formal calibration analysis (no reliability diagram, Brier score, or isotonic "
        "regression was performed). The model's known label-dependency tautology (rms/kurtosis "
        "are both input features and labeling criteria - see model_metadata.json) means high "
        "confidence here reflects confident reproduction of the derived labeling rule, not "
        "independently validated certainty about bearing health.",
        "test_count": len(y_test),
        "confidence_vs_correctness": {
            "mean_confidence_correct": mean_conf_correct,
            "mean_confidence_incorrect": mean_conf_incorrect,
            "median_confidence_correct": median_conf_correct,
            "median_confidence_incorrect": median_conf_incorrect,
            "n_correct": int(correct.sum()),
            "n_incorrect": int((~correct).sum()),
        },
        "thresholds": threshold_results,
    }
    (MODEL_DIR / "confidence_analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved {MODEL_DIR / 'confidence_analysis.json'}")


if __name__ == "__main__":
    main()
