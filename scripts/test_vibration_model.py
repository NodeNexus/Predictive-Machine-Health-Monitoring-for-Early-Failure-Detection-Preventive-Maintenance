#!/usr/bin/env python
"""CLI: run the Vibration ML V1 baseline model on a real IMS vibration
sample/window.

Usage:
    python scripts/test_vibration_model.py --file "<path to an IMS data file>" [--channel 4]

Prints the predicted class, probabilities, and the underlying features -
and prominently repeats the tautology caveat from model_metadata.json so
this is never mistaken for a validated fault-detection result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipelines.vibration.features import extract_vibration_features  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "models" / "vibration" / "vibration_baseline_v1.joblib"
METADATA_PATH = REPO_ROOT / "models" / "vibration" / "model_metadata.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Vibration ML V1 baseline on one real IMS file.")
    parser.add_argument("--file", required=True, help="Path to an IMS ASCII data file.")
    parser.add_argument("--channel", type=int, default=4, help="0-indexed column to use (default 4 = bearing 3).")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f"Error: file not found: {file_path}")
        raise SystemExit(1)

    if not MODEL_PATH.is_file():
        print(f"Error: model not found: {MODEL_PATH}. Run ml/vibration/train.py first.")
        raise SystemExit(1)

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    feature_columns = metadata["feature_columns"]
    class_names = metadata["class_names"]

    data = np.loadtxt(file_path)
    window = data[:, args.channel]
    features = extract_vibration_features(window, sample_rate=20000.0)
    feature_values = {col: getattr(features, col) for col in feature_columns}

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    scaler = bundle.get("scaler")

    X = np.array([[feature_values[col] for col in feature_columns]])
    if scaler is not None:
        X = scaler.transform(X)

    pred_idx = model.predict(X)[0]
    probs = model.predict_proba(X)[0] if hasattr(model, "predict_proba") else None

    print(f"File: {file_path.name} (channel {args.channel})")
    print(f"Predicted class: {class_names[pred_idx]}")
    if probs is not None:
        print("Class probabilities:")
        for name, p in sorted(zip(class_names, probs), key=lambda x: -x[1]):
            print(f"  {name}: {p:.4f}")
    print("\nFeatures used:")
    for col, val in feature_values.items():
        print(f"  {col}: {val:.4f}")

    print(
        "\nCAUTION: this label was derived from a documented statistical rule, not "
        "original dataset ground truth, and the model's near-perfect test score is "
        "partly a tautology (rms/kurtosis are both labeling criteria and input "
        "features) - see models/vibration/model_metadata.json before drawing "
        "conclusions."
    )


if __name__ == "__main__":
    main()
