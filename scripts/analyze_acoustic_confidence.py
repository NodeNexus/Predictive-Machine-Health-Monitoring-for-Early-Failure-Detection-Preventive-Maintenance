#!/usr/bin/env python
"""ACOUSTIC ML V1 CONFIDENCE GATE - steps 1+2: probability/threshold sweep
and calibration check on the deployment candidate (Logistic Regression,
models/acoustic/acoustic_baseline_v1.joblib), evaluated on the UNTOUCHED
test split only.

Calibration is measured directly (Brier score + Expected Calibration
Error over confidence bins) rather than assumed from the model outputting
probabilities.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.acoustic.dataset import build_feature_matrix, load_split_manifest, records_for_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "models" / "acoustic"
LABEL_NAMES = ["normal", "anomaly"]
THRESHOLDS = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99]
N_CALIBRATION_BINS = 10


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, n_bins: int = N_CALIBRATION_BINS) -> dict:
    """Standard ECE: bin by predicted confidence (of the predicted class,
    i.e. max(p, 1-p)), compare mean confidence to observed accuracy per bin,
    weight by bin size."""
    bin_edges = np.linspace(0.5, 1.0, n_bins + 1)  # confidence is always >= 0.5 for the argmax class
    bin_indices = np.digitize(confidence, bin_edges[1:-1])
    ece = 0.0
    bins = []
    n = len(confidence)
    for b in range(n_bins):
        mask = bin_indices == b
        count = int(mask.sum())
        if count == 0:
            bins.append({"bin_range": [float(bin_edges[b]), float(bin_edges[b + 1])], "count": 0})
            continue
        mean_conf = float(confidence[mask].mean())
        mean_acc = float(correct[mask].mean())
        gap = abs(mean_conf - mean_acc)
        ece += (count / n) * gap
        bins.append(
            {
                "bin_range": [float(bin_edges[b]), float(bin_edges[b + 1])],
                "count": count,
                "mean_confidence": mean_conf,
                "observed_accuracy": mean_acc,
                "gap": gap,
            }
        )
    return {"ece": ece, "bins": bins}


def main() -> None:
    import joblib

    manifest = load_split_manifest()
    test_records = records_for_split(manifest, "test")
    X_test, y_test, groups_test = build_feature_matrix(test_records)

    bundle = joblib.load(MODEL_DIR / "acoustic_baseline_v1.joblib")
    model = bundle["model"]
    scaler = bundle.get("scaler")
    X = scaler.transform(X_test) if scaler is not None else X_test

    probs_anomaly = model.predict_proba(X)[:, 1]
    preds = (probs_anomaly >= 0.5).astype(int)  # the model's own default decision boundary
    confidence = np.where(preds == 1, probs_anomaly, 1 - probs_anomaly)  # confidence in the PREDICTED class
    correct = preds == y_test

    mean_conf_correct = float(confidence[correct].mean()) if correct.any() else None
    mean_conf_incorrect = float(confidence[~correct].mean()) if (~correct).any() else None
    median_conf_correct = float(np.median(confidence[correct])) if correct.any() else None
    median_conf_incorrect = float(np.median(confidence[~correct])) if (~correct).any() else None

    brier = float(brier_score_loss(y_test, probs_anomaly))
    ece_result = expected_calibration_error(confidence, correct.astype(float))

    threshold_results = []
    for t in THRESHOLDS:
        accepted_mask = confidence >= t
        n_accepted = int(accepted_mask.sum())
        n_rejected = int((~accepted_mask).sum())
        entry = {
            "threshold": t,
            "accepted": n_accepted,
            "rejected": n_rejected,
            "coverage": n_accepted / len(y_test),
        }
        if n_accepted > 0:
            y_acc = y_test[accepted_mask]
            p_acc = preds[accepted_mask]
            entry["accuracy_on_accepted"] = float((y_acc == p_acc).mean())
            entry["macro_f1_on_accepted"] = float(f1_score(y_acc, p_acc, average="macro", zero_division=0))
            if len(set(y_acc.tolist())) > 1 or 1 in set(p_acc.tolist()):
                entry["anomaly_precision"] = float(precision_score(y_acc, p_acc, pos_label=1, zero_division=0))
                entry["anomaly_recall"] = float(recall_score(y_acc, p_acc, pos_label=1, zero_division=0))
            else:
                entry["anomaly_precision"] = None
                entry["anomaly_recall"] = None
            cm = confusion_matrix(y_acc, p_acc, labels=[0, 1])
            entry["confusion_matrix_on_accepted"] = cm.tolist()
            # false_negative = true anomaly (1) predicted normal (0); false_positive = true normal (0) predicted anomaly (1)
            entry["false_negative_count"] = int(cm[1][0]) if cm.shape == (2, 2) else None
            entry["false_positive_count"] = int(cm[0][1]) if cm.shape == (2, 2) else None
        else:
            entry.update(
                {
                    "accuracy_on_accepted": None,
                    "macro_f1_on_accepted": None,
                    "anomaly_precision": None,
                    "anomaly_recall": None,
                    "confusion_matrix_on_accepted": None,
                    "false_negative_count": None,
                    "false_positive_count": None,
                }
            )
        threshold_results.append(entry)
        print(
            f"t={t:.2f} coverage={entry['coverage']:.3f} acc={entry['accuracy_on_accepted']} "
            f"macro_f1={entry['macro_f1_on_accepted']} anomaly_p={entry['anomaly_precision']} "
            f"anomaly_r={entry['anomaly_recall']} FN={entry['false_negative_count']} FP={entry['false_positive_count']}"
        )

    # unaccepted (suppressed) anomalies at each threshold - the operational
    # cost of "excessive suppression": how many TRUE anomalies get
    # suppressed to "uncertain" rather than surfaced at all.
    suppressed_true_anomalies = {}
    for t in THRESHOLDS:
        accepted_mask = confidence >= t
        suppressed_mask = ~accepted_mask
        suppressed_true_anomalies[str(t)] = int(((y_test == 1) & suppressed_mask).sum())

    result = {
        "model": "logistic_regression (acoustic-v1)",
        "test_count": len(y_test),
        "default_decision_boundary": 0.5,
        "confidence_definition": "max(p_anomaly, 1 - p_anomaly) - confidence in whichever class was predicted",
        "confidence_vs_correctness": {
            "mean_confidence_correct": mean_conf_correct,
            "mean_confidence_incorrect": mean_conf_incorrect,
            "median_confidence_correct": median_conf_correct,
            "median_confidence_incorrect": median_conf_incorrect,
            "n_correct": int(correct.sum()),
            "n_incorrect": int((~correct).sum()),
        },
        "calibration": {
            "brier_score": brier,
            "brier_score_note": "Lower is better; 0=perfect, 0.25=uninformative-coin-flip baseline for balanced "
            "classes (this dataset is imbalanced ~11:1, so compare cautiously). Computed directly - not assumed.",
            "expected_calibration_error": ece_result["ece"],
            "ece_bins": ece_result["bins"],
            "calibration_verdict": "Computed via a real 10-bin ECE + Brier score on the test set (see values above) "
            "- this is NOT a claim that the model is well-calibrated merely because it outputs probabilities; "
            "read the ece/brier numbers themselves to judge that.",
        },
        "suppressed_true_anomalies_by_threshold": suppressed_true_anomalies,
        "thresholds": threshold_results,
    }
    (MODEL_DIR / "confidence_analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nBrier score: {brier:.4f}")
    print(f"ECE: {ece_result['ece']:.4f}")
    print(f"\nSaved {MODEL_DIR / 'confidence_analysis.json'}")


if __name__ == "__main__":
    main()
