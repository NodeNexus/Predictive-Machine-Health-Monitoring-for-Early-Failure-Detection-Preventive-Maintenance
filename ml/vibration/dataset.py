"""Builds the leak-resistant train/validation/test split for Vibration ML
V1 (IMS 1st_test, channel 4) and the feature matrix used by the baseline
models.

SPLIT STRATEGY (documented, not arbitrary):

A pure global chronological 70/15/15 cut was tried first and rejected: it
put only 20 of 323 "severe" files (1.3%) in train and 264 (82%) in test -
the model would have almost nothing to learn "severe" from, since that
label is heavily back-loaded in time (real bearing spalling worsens near
end-of-life, so "severe" files are naturally concentrated late in the run).

Instead: the timeline is divided into contiguous 20-file blocks (preserving
temporal adjacency - no individual files are shuffled). Each block is
assigned a "dominant label" only for the purpose of deciding which stratum
it belongs to (each file keeps its own true derived label regardless).
Within each dominant-label stratum, blocks are sorted chronologically and
split 70/15/15 (earliest blocks -> train, middle -> validation, latest ->
test) - so temporal order is still respected WITHIN each class, while
every class gets real train/validation/test representation instead of
being wiped out by the global back-loading of "severe".

This is the "another explicitly defensible grouping strategy" allowed by
the task brief when pure global chronological splitting isn't viable -
adjacent files are still never split across train and test in a way that
breaks a block's temporal contiguity; the residual risk is only at the
handful of stratum-internal block boundaries, not for every file pair.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from ml.vibration.labeling import BaselineStats, build_labeled_records

REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_PATH = REPO_ROOT / "data" / "manifests" / "vibration_ims_ch4_trajectory.json"
SPLIT_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "vibration_ml_v1_split.json"

BLOCK_SIZE = 20
TRAIN_FRAC = 0.70
VAL_FRAC = 0.15

FEATURE_COLUMNS = [
    "rms", "std", "crest_factor", "kurtosis", "skewness",
    "peak", "peak_to_peak", "dominant_frequency", "spectral_centroid", "spectral_bandwidth",
]


def _dominant_label(block: list[dict]) -> str:
    return Counter(r["label_3class"] for r in block).most_common(1)[0][0]


def build_split(labeled_records: list[dict]) -> list[dict]:
    n = len(labeled_records)
    blocks = [labeled_records[i : i + BLOCK_SIZE] for i in range(0, n, BLOCK_SIZE)]
    block_labels = [_dominant_label(b) for b in blocks]

    strata: dict[str, list[int]] = {}
    for i, label in enumerate(block_labels):
        strata.setdefault(label, []).append(i)

    block_split: dict[int, str] = {}
    for label, block_indices in strata.items():
        block_indices = sorted(block_indices)  # already chronological, kept explicit
        m = len(block_indices)
        train_end = round(m * TRAIN_FRAC)
        val_end = train_end + round(m * VAL_FRAC)
        for j, bi in enumerate(block_indices):
            if j < train_end:
                block_split[bi] = "train"
            elif j < val_end:
                block_split[bi] = "validation"
            else:
                block_split[bi] = "test"

    result = []
    for block_idx, block in enumerate(blocks):
        split = block_split[block_idx]
        for r in block:
            result.append({**r, "block_index": block_idx, "block_dominant_label": block_labels[block_idx], "split": split})
    return result


def build_feature_matrix(records: list[dict], feature_columns: list[str] = FEATURE_COLUMNS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (X, y_3class_encoded, groups) for a list of manifest records
    all belonging to the same split."""
    label_to_idx = {"healthy": 0, "degrading": 1, "severe": 2}
    X = np.array([[r[col] for col in feature_columns] for r in records], dtype=np.float64)
    y = np.array([label_to_idx[r["label_3class"]] for r in records], dtype=np.int64)
    groups = np.array([r["block_index"] for r in records], dtype=np.int64)
    return X, y, groups


def load_split_manifest(path: Path = SPLIT_MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def records_for_split(manifest: dict, split: str) -> list[dict]:
    return [r for r in manifest["records"] if r["split"] == split]
