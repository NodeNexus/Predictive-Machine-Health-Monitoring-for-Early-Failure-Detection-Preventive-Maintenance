#!/usr/bin/env python
"""Builds the Vibration ML V1 task definition, labels, and leak-resistant
split for IMS 1st_test, channel 4 (bearing 3).

This does NOT train a model - it only extracts features from every real
file (via the existing, already-validated vibration feature pipeline),
derives labels via a documented statistical rule (NOT original dataset
ground truth - the dataset provides none), and writes:

  models/vibration/vibration_task_definition.json  - the task/label decision + reasoning
  data/manifests/vibration_ims_ch4_trajectory.json - raw per-file feature trajectory
  data/manifests/vibration_ml_v1_split.json        - the leak-resistant train/val/test manifest

Rerunnable and deterministic (no randomness involved at all - purely
derived from the real files' own timestamps/order and the documented
z-score rule).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.pipelines.vibration.features import extract_vibration_features  # noqa: E402
from ml.vibration.dataset import BLOCK_SIZE, FEATURE_COLUMNS, TRAIN_FRAC, VAL_FRAC, build_split  # noqa: E402
from ml.vibration.labeling import (  # noqa: E402
    BASELINE_END_INDEX,
    HEALTHY_Z_THRESHOLD,
    SEVERE_Z_THRESHOLD,
    build_labeled_records,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test"
CHANNEL = 4
SAMPLE_RATE = 20000.0

TRAJECTORY_PATH = REPO_ROOT / "data" / "manifests" / "vibration_ims_ch4_trajectory.json"
SPLIT_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "vibration_ml_v1_split.json"
TASK_DEFINITION_PATH = REPO_ROOT / "models" / "vibration" / "vibration_task_definition.json"


def extract_trajectory() -> list[dict]:
    files = sorted(p for p in TEST_DIR.iterdir() if p.is_file())
    print(f"Extracting features from {len(files)} real files (this reads every file - ~90s)...")
    records = []
    start = time.time()
    for idx, f in enumerate(files):
        data = np.loadtxt(f)
        window = data[:, CHANNEL]
        feat = extract_vibration_features(window, sample_rate=SAMPLE_RATE)
        records.append(
            {
                "index": idx,
                "file": f.name,
                "rms": feat.rms,
                "std": feat.std,
                "crest_factor": feat.crest_factor,
                "kurtosis": feat.kurtosis,
                "skewness": feat.skewness,
                "peak": feat.peak,
                "peak_to_peak": feat.peak_to_peak,
                "dominant_frequency": feat.dominant_frequency,
                "spectral_centroid": feat.spectral_centroid,
                "spectral_bandwidth": feat.spectral_bandwidth,
            }
        )
        if idx % 500 == 0:
            print(f"  {idx}/{len(files)} ({time.time()-start:.0f}s)")
    print(f"Done in {time.time()-start:.0f}s")
    return records


def main() -> None:
    if TRAJECTORY_PATH.is_file():
        print(f"Reusing existing trajectory: {TRAJECTORY_PATH}")
        records = json.loads(TRAJECTORY_PATH.read_text(encoding="utf-8"))["records"]
    else:
        records = extract_trajectory()
        TRAJECTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        TRAJECTORY_PATH.write_text(
            json.dumps({"source": str(TEST_DIR), "channel": CHANNEL, "sample_rate": SAMPLE_RATE, "records": records}, indent=2),
            encoding="utf-8",
        )

    labeled, baseline = build_labeled_records(records)
    split_records = build_split(labeled)

    counts_by_split_and_label = Counter((r["split"], r["label_3class"]) for r in split_records)
    print("\nPer-split, per-label counts:")
    for split in ("train", "validation", "test"):
        row = {label: counts_by_split_and_label.get((split, label), 0) for label in ("healthy", "degrading", "severe")}
        print(f"  {split:10s}: {row}  total={sum(row.values())}")

    SPLIT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_directory": str(TEST_DIR),
        "channel": CHANNEL,
        "sample_rate": SAMPLE_RATE,
        "feature_columns": FEATURE_COLUMNS,
        "block_size": BLOCK_SIZE,
        "train_fraction_target": TRAIN_FRAC,
        "validation_fraction_target": VAL_FRAC,
        "label_rule": {
            "baseline_end_index": BASELINE_END_INDEX,
            "healthy_z_threshold": HEALTHY_Z_THRESHOLD,
            "severe_z_threshold": SEVERE_Z_THRESHOLD,
            "baseline_stats": {
                "rms_mean": baseline.rms_mean, "rms_std": baseline.rms_std,
                "kurtosis_mean": baseline.kurtosis_mean, "kurtosis_std": baseline.kurtosis_std,
            },
            "description": (
                "healthy: z_rms < 3.0. severe: z_kurtosis >= 10.0 (regardless of z_rms, "
                "which saturates early and stops being informative past fault onset). "
                "degrading: everything else. Labels are DERIVED, not original dataset "
                "ground truth - see models/vibration/vibration_task_definition.json."
            ),
        },
        "records": [
            {
                "source_file": r["file"],
                "chronological_index": r["index"],
                "channel": CHANNEL,
                "block_index": r["block_index"],
                "block_dominant_label": r["block_dominant_label"],
                "split": r["split"],
                "label_3class": r["label_3class"],
                "label_binary": r["label_binary"],
                "health_index": r["health_index"],
                "z_rms": r["z_rms"],
                "z_kurtosis": r["z_kurtosis"],
                "features": {col: r[col] for col in FEATURE_COLUMNS},
            }
            for r in split_records
        ],
    }
    SPLIT_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nSplit manifest written to {SPLIT_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
