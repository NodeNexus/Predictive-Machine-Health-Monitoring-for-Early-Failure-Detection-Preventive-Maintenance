#!/usr/bin/env python
"""CLI: run the Acoustic ML V1 baseline model on a real WAV file.

Usage:
    python scripts/test_acoustic_model.py --file "<path to a WAV file>"

Prints the predicted class, probability, and the underlying feature
summary. Unlike the Vibration ML V1 model, normal/anomaly here ARE the
dataset's own native vendor-assigned labels (not project-derived) - see
models/acoustic/model_metadata.json's label_provenance_note. This script
still prints the robustness caveat (performance may vary by recording
section/domain - see model_metadata.json's robustness_by_section_domain_group)
so results are never read as a universal, condition-independent guarantee.
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipelines.acoustic.features import extract_acoustic_features  # noqa: E402
from ml.acoustic.dataset import FEATURE_COLUMNS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "models" / "acoustic" / "acoustic_baseline_v1.joblib"
METADATA_PATH = REPO_ROOT / "models" / "acoustic" / "model_metadata.json"


def extract_features(path: Path) -> dict:
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    window = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0

    octave_features = extract_acoustic_features(window, sample_rate=sample_rate, band_type="octave")
    third_octave_features = extract_acoustic_features(window, sample_rate=sample_rate, band_type="third_octave")

    flat = {
        "rms": octave_features.rms,
        "peak_amplitude": octave_features.peak_amplitude,
        "crest_factor": octave_features.crest_factor,
        "energy": octave_features.energy,
        "dominant_frequency": octave_features.dominant_frequency,
        "spectral_centroid": octave_features.spectral_centroid,
        "spectral_bandwidth": octave_features.spectral_bandwidth,
        "spectral_rolloff": octave_features.spectral_rolloff,
        "spectral_flatness": octave_features.spectral_flatness,
        "top_spectral_peak_frequency": octave_features.spectral_peaks[0].frequency if octave_features.spectral_peaks else 0.0,
        "top_spectral_peak_magnitude": octave_features.spectral_peaks[0].magnitude if octave_features.spectral_peaks else 0.0,
    }
    for i, band in enumerate(octave_features.band_energies.bands):
        flat[f"octave_band_{i}"] = band.energy
    for i, band in enumerate(third_octave_features.band_energies.bands):
        flat[f"third_octave_band_{i}"] = band.energy
    for i, coeff in enumerate(octave_features.mfcc):
        flat[f"mfcc_{i}"] = coeff
    return flat


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Acoustic ML V1 baseline on one real WAV file.")
    parser.add_argument("--file", required=True, help="Path to a WAV file (16kHz mono 16-bit PCM expected).")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f"Error: file not found: {file_path}")
        raise SystemExit(1)
    if not MODEL_PATH.is_file():
        print(f"Error: model not found: {MODEL_PATH}. Run ml/acoustic/train.py first.")
        raise SystemExit(1)

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    class_names = metadata["class_names"]

    feature_values = extract_features(file_path)
    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    scaler = bundle.get("scaler")

    X = np.array([[feature_values[col] for col in FEATURE_COLUMNS]])
    if scaler is not None:
        X = scaler.transform(X)

    pred_idx = model.predict(X)[0]
    probs = model.predict_proba(X)[0] if hasattr(model, "predict_proba") else None

    print(f"File: {file_path.name}")
    print(f"Predicted class: {class_names[pred_idx]}")
    if probs is not None:
        print("Class probabilities:")
        for name, p in sorted(zip(class_names, probs), key=lambda x: -x[1]):
            print(f"  {name}: {p:.4f}")

    print("\nKey features:")
    for col in ("rms", "crest_factor", "spectral_centroid", "spectral_flatness", "mfcc_0", "mfcc_1"):
        print(f"  {col}: {feature_values[col]:.4f}")

    print(
        "\nNOTE: normal/anomaly are the dataset's own native labels (not project-derived), unlike "
        "Vibration ML V1's derived labels. However, this model's robustness across recording "
        "section/domain/velocity was only partially verified - see "
        "models/acoustic/model_metadata.json's robustness_by_section_domain_group before treating "
        "this prediction as condition-independent."
    )


if __name__ == "__main__":
    main()
