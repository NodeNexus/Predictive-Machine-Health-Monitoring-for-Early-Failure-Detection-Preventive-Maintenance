#!/usr/bin/env python
"""ACOUSTIC ML V1 - steps 2+3: leak-safe split + feature extraction.

Extracts the full existing acoustic feature set (reused, not reimplemented)
for all 3599 real WAV files, builds the stratified (section, domain, label)
split, and writes data/manifests/acoustic_ml_v1_split.json.

Real feature extraction across ~3599 ten-second clips is the dominant cost
here (~0.22s/file measured, ~13 minutes total) - this script prints
progress every 200 files so a long run is observable.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ml.acoustic.dataset import (  # noqa: E402
    FEATURE_COLUMNS,
    build_split,
    extract_features_for_record,
    load_inventory,
)

SPLIT_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "acoustic_ml_v1_split.json"


def main() -> None:
    records = load_inventory()
    print(f"Loaded {len(records)} inventory records")

    t0 = time.time()
    for i, r in enumerate(records):
        r["features"] = extract_features_for_record(r)
        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(records) - i - 1) / rate
            print(f"  {i + 1}/{len(records)} files done ({elapsed:.1f}s elapsed, ETA {eta:.1f}s)")

    print(f"Feature extraction complete in {time.time() - t0:.1f}s")

    split_records = build_split(records)

    counts_by_split_label = {}
    for r in split_records:
        key = (r["split"], r["label"])
        counts_by_split_label[key] = counts_by_split_label.get(key, 0) + 1
    print("Split x label counts:", counts_by_split_label)

    manifest = {
        "dataset_dir": "DATASET/bearing/bearing",
        "sample_rate": 16000.0,
        "clip_duration_seconds": 10.0,
        "feature_columns": FEATURE_COLUMNS,
        "split_seed": 42,
        "split_strategy": "stratified_by_section_domain_label",
        "train_frac_target": 0.70,
        "validation_frac_target": 0.15,
        "test_frac_target": 0.15,
        "records": split_records,
    }
    SPLIT_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {SPLIT_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
