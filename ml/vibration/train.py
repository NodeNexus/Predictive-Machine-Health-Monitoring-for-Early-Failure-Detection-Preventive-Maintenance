#!/usr/bin/env python
"""Trains and compares baseline classical ML models for Vibration ML V1
(3-class: healthy/degrading/severe) on the leak-resistant split.

Deliberately classical, not deep: Logistic Regression, Random Forest, and
Gradient Boosting (all from scikit-learn, already in the environment - no
new dependency added). This is baseline discovery, not extensive tuning.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.vibration.dataset import FEATURE_COLUMNS, build_feature_matrix, load_split_manifest, records_for_split  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "models" / "vibration"
LABEL_NAMES = ["healthy", "degrading", "severe"]


def evaluate(model, X, y, label_names=LABEL_NAMES) -> dict:
    preds = model.predict(X)
    report = classification_report(y, preds, target_names=label_names, output_dict=True, zero_division=0)
    cm = confusion_matrix(y, preds, labels=list(range(len(label_names))))
    macro_f1 = f1_score(y, preds, average="macro", zero_division=0)
    return {"report": report, "confusion_matrix": cm.tolist(), "macro_f1": macro_f1, "predictions": preds.tolist()}


def main() -> None:
    manifest = load_split_manifest()
    train_records = [{**r, **r["features"]} for r in records_for_split(manifest, "train")]
    val_records = [{**r, **r["features"]} for r in records_for_split(manifest, "validation")]
    test_records = [{**r, **r["features"]} for r in records_for_split(manifest, "test")]

    X_train, y_train, _ = build_feature_matrix(train_records)
    X_val, y_val, _ = build_feature_matrix(val_records)
    X_test, y_test, _ = build_feature_matrix(test_records)

    print(f"train={len(X_train)} validation={len(X_val)} test={len(X_test)}")

    scaler = StandardScaler().fit(X_train)
    X_train_s, X_val_s, X_test_s = scaler.transform(X_train), scaler.transform(X_val), scaler.transform(X_test)

    class_weight = "balanced"  # honest necessity: severe/healthy are minority classes
    models = {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight=class_weight, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=200, class_weight=class_weight, random_state=42),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),  # no native class_weight support
    }

    results = {}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in models.items():
        X_tr = X_train_s if name == "logistic_regression" else X_train
        X_va = X_val_s if name == "logistic_regression" else X_val
        model.fit(X_tr, y_train)
        val_result = evaluate(model, X_va, y_val)
        results[name] = {"model": model, "val_macro_f1": val_result["macro_f1"], "val_report": val_result["report"]}
        print(f"{name}: val_macro_f1={val_result['macro_f1']:.4f}")

    best_name = max(results, key=lambda n: results[n]["val_macro_f1"])
    best_model = results[best_name]["model"]
    print(f"\nBest model on validation: {best_name} (val_macro_f1={results[best_name]['val_macro_f1']:.4f})")

    X_test_final = X_test_s if best_name == "logistic_regression" else X_test
    test_result = evaluate(best_model, X_test_final, y_test)

    print(f"\nTest results for {best_name}:")
    print(f"Macro F1: {test_result['macro_f1']:.4f}")
    print(json.dumps(test_result["report"], indent=2))
    print("Confusion matrix (rows=true, cols=predicted), order=", LABEL_NAMES)
    for row in test_result["confusion_matrix"]:
        print(row)

    # feature importance / coefficients
    importance = None
    if hasattr(best_model, "feature_importances_"):
        importance = dict(zip(FEATURE_COLUMNS, best_model.feature_importances_.tolist()))
    elif hasattr(best_model, "coef_"):
        importance = {col: float(np.abs(best_model.coef_[:, i]).mean()) for i, col in enumerate(FEATURE_COLUMNS)}
    if importance:
        print("\nFeature importance:")
        for k, v in sorted(importance.items(), key=lambda kv: -kv[1]):
            print(f"  {k}: {v:.4f}")

    joblib.dump({"model": best_model, "scaler": scaler if best_name == "logistic_regression" else None}, MODEL_DIR / "vibration_baseline_v1.joblib")

    all_val_reports = {name: r["val_report"] for name, r in results.items()}
    metadata = {
        "model_name": best_name,
        "model_version": "vibration-v1",
        "dataset": "IMS_1st_test_channel4",
        "class_names": LABEL_NAMES,
        "feature_columns": FEATURE_COLUMNS,
        "random_seed": 42,
        "train_count": len(X_train),
        "validation_count": len(X_val),
        "test_count": len(X_test),
        "test_macro_f1": test_result["macro_f1"],
        "test_report": test_result["report"],
        "test_confusion_matrix": test_result["confusion_matrix"],
        "feature_importance": importance,
        "all_models_val_macro_f1": {name: r["val_macro_f1"] for name, r in results.items()},
    }
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nModel saved to {MODEL_DIR / 'vibration_baseline_v1.joblib'}")
    print(f"Metadata saved to {MODEL_DIR / 'model_metadata.json'}")


if __name__ == "__main__":
    main()
