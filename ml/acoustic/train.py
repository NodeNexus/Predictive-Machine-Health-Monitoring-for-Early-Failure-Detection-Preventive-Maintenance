#!/usr/bin/env python
"""Trains and compares baseline classical ML models for Acoustic ML V1
(binary: normal/anomaly) on the leak-resistant, stratified split.

Deliberately classical, not deep: Logistic Regression, Random Forest, and
Gradient Boosting (all scikit-learn, already in the environment - no new
dependency). Class imbalance (anomaly is ~9% of the pool) is handled via
class_weight='balanced' where supported; GradientBoostingClassifier has no
native class_weight, so it is fit on the same imbalanced data as a direct
comparison point rather than silently rebalanced underneath it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.acoustic.dataset import FEATURE_COLUMNS, build_feature_matrix, load_split_manifest, records_for_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "models" / "acoustic"
LABEL_NAMES = ["normal", "anomaly"]


def evaluate(model, X, y, label_names=LABEL_NAMES) -> dict:
    preds = model.predict(X)
    report = classification_report(y, preds, target_names=label_names, output_dict=True, zero_division=0)
    cm = confusion_matrix(y, preds, labels=[0, 1])
    macro_f1 = f1_score(y, preds, average="macro", zero_division=0)
    result = {"report": report, "confusion_matrix": cm.tolist(), "macro_f1": macro_f1, "predictions": preds.tolist()}
    if hasattr(model, "predict_proba"):
        proba_anomaly = model.predict_proba(X)[:, 1]
        result["roc_auc"] = float(roc_auc_score(y, proba_anomaly)) if len(set(y.tolist())) > 1 else None
        result["pr_auc"] = float(average_precision_score(y, proba_anomaly)) if len(set(y.tolist())) > 1 else None
        result["probabilities"] = proba_anomaly.tolist()
    return result


def main() -> None:
    manifest = load_split_manifest()
    train_records = records_for_split(manifest, "train")
    val_records = records_for_split(manifest, "validation")
    test_records = records_for_split(manifest, "test")

    X_train, y_train, groups_train = build_feature_matrix(train_records)
    X_val, y_val, _ = build_feature_matrix(val_records)
    X_test, y_test, groups_test = build_feature_matrix(test_records)

    print(f"train={len(X_train)} validation={len(X_val)} test={len(X_test)}")
    print(f"train label counts: normal={int((y_train == 0).sum())} anomaly={int((y_train == 1).sum())}")
    print(f"test label counts: normal={int((y_test == 0).sum())} anomaly={int((y_test == 1).sum())}")

    scaler = StandardScaler().fit(X_train)
    X_train_s, X_val_s, X_test_s = scaler.transform(X_train), scaler.transform(X_val), scaler.transform(X_test)

    models = {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),  # no native class_weight support
    }

    results = {}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        X_tr = X_train_s if name == "logistic_regression" else X_train
        X_va = X_val_s if name == "logistic_regression" else X_val
        model.fit(X_tr, y_train)
        val_result = evaluate(model, X_va, y_val)
        results[name] = {
            "model": model,
            "val_macro_f1": val_result["macro_f1"],
            "val_roc_auc": val_result.get("roc_auc"),
            "val_pr_auc": val_result.get("pr_auc"),
            "val_report": val_result["report"],
        }
        print(
            f"{name}: val_macro_f1={val_result['macro_f1']:.4f} "
            f"val_roc_auc={val_result.get('roc_auc')} val_pr_auc={val_result.get('pr_auc')}"
        )

    best_name = max(results, key=lambda n: results[n]["val_macro_f1"])
    best_model = results[best_name]["model"]
    print(f"\nBest model on validation (by macro F1): {best_name} (val_macro_f1={results[best_name]['val_macro_f1']:.4f})")

    X_test_final = X_test_s if best_name == "logistic_regression" else X_test
    test_result = evaluate(best_model, X_test_final, y_test)

    print(f"\nTest results for {best_name}:")
    print(f"Macro F1: {test_result['macro_f1']:.4f}")
    print(f"ROC-AUC: {test_result.get('roc_auc')}")
    print(f"PR-AUC: {test_result.get('pr_auc')}")
    print(json.dumps(test_result["report"], indent=2))
    print("Confusion matrix (rows=true, cols=predicted), order=", LABEL_NAMES)
    for row in test_result["confusion_matrix"]:
        print(row)

    # Also evaluate every OTHER trained model on test, for the report's
    # "models tested" comparison table (not just the winner).
    all_test_results = {}
    for name, r in results.items():
        model = r["model"]
        X_te = X_test_s if name == "logistic_regression" else X_test
        res = evaluate(model, X_te, y_test)
        all_test_results[name] = {
            "test_macro_f1": res["macro_f1"],
            "test_roc_auc": res.get("roc_auc"),
            "test_pr_auc": res.get("pr_auc"),
            "test_accuracy": res["report"]["accuracy"],
        }
        print(f"[all-models test] {name}: {all_test_results[name]}")

    importance = None
    if hasattr(best_model, "feature_importances_"):
        importance = dict(zip(FEATURE_COLUMNS, best_model.feature_importances_.tolist()))
    elif hasattr(best_model, "coef_"):
        importance = {col: float(np.abs(best_model.coef_[:, i]).mean()) for i, col in enumerate(FEATURE_COLUMNS)}
    if importance:
        print("\nTop 15 feature importances:")
        for k, v in sorted(importance.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {k}: {v:.4f}")

    # --- robustness check: performance broken down by (section, domain) ---
    robustness = {}
    for group in sorted(set(groups_test.tolist())):
        mask = groups_test == group
        if mask.sum() == 0 or len(set(y_test[mask].tolist())) < 2:
            robustness[group] = {"n": int(mask.sum()), "note": "insufficient class diversity in this group's test slice"}
            continue
        group_preds = best_model.predict(X_test_final[mask])
        group_acc = float((group_preds == y_test[mask]).mean())
        group_f1 = f1_score(y_test[mask], group_preds, average="macro", zero_division=0)
        robustness[group] = {"n": int(mask.sum()), "accuracy": group_acc, "macro_f1": float(group_f1)}
    print("\nRobustness by (section|domain) group:")
    for g, r in robustness.items():
        print(f"  {g}: {r}")

    joblib.dump(
        {"model": best_model, "scaler": scaler if best_name == "logistic_regression" else None},
        MODEL_DIR / "acoustic_baseline_v1.joblib",
    )

    metadata = {
        "model_name": best_name,
        "model_version": "acoustic-v1",
        "dataset": "DATASET/bearing/bearing (DCASE-style domain-generalization bearing acoustic dataset)",
        "class_names": LABEL_NAMES,
        "feature_columns": FEATURE_COLUMNS,
        "random_seed": 42,
        "train_count": len(X_train),
        "validation_count": len(X_val),
        "test_count": len(X_test),
        "test_macro_f1": test_result["macro_f1"],
        "test_roc_auc": test_result.get("roc_auc"),
        "test_pr_auc": test_result.get("pr_auc"),
        "test_report": test_result["report"],
        "test_confusion_matrix": test_result["confusion_matrix"],
        "feature_importance": importance,
        "all_models_val_macro_f1": {name: r["val_macro_f1"] for name, r in results.items()},
        "all_models_test_comparison": all_test_results,
        "robustness_by_section_domain_group": robustness,
        "class_imbalance_handling": "class_weight='balanced' for logistic_regression and random_forest; "
        "gradient_boosting has no native class_weight support and was fit on the natural ~11:1 "
        "normal:anomaly ratio as a direct, undistorted comparison point.",
        "labels_are_native_dataset_ground_truth": True,
        "label_provenance_note": "Unlike the Vibration ML V1 task, normal/anomaly here are the dataset's "
        "OWN vendor-assigned labels, not derived by this project.",
    }
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nModel saved to {MODEL_DIR / 'acoustic_baseline_v1.joblib'}")
    print(f"Metadata saved to {MODEL_DIR / 'model_metadata.json'}")


if __name__ == "__main__":
    main()
