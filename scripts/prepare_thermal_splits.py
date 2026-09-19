#!/usr/bin/env python
"""Builds leak-resistant train/validation/test splits for the two thermal
motor datasets, and writes machine-readable manifests.

This script does NOT train anything, does NOT touch the existing IDEA LAB
thermal pipeline, and does NOT copy images - manifests reference the
original files in place.

Grouping methodology (see docs/THERMAL_SPLIT_REPORT.md for the full
justification):

Dataset 1 (Induction Motor-Thermal Images):
    Each class is one single continuous FLIR capture session (confirmed via
    embedded ASCII timestamps - real acquisition metadata, not inferred
    from file order). A perceptual-hash (dHash) check of consecutive frames
    found NO clean bimodal "duplicate vs distinct" gap - similarity decays
    smoothly as the session progresses (the motor's thermal state evolves
    continuously). Because there is no defensible similarity threshold to
    cluster on, and because temporal proximity is confirmed to correlate
    with visual similarity, this dataset is split chronologically per
    class (train = earliest images, val = next, test = latest), with a
    small buffer of images dropped at each cut boundary to reduce residual
    near-duplicate risk at the two boundary points.

Dataset 2 (IR-Motor-bmp, 11 classes):
    No reliable acquisition-order metadata exists (BMP carries no EXIF;
    file-modification timestamps were checked and found to be internally
    INCONSISTENT with filename order and with irregular multi-minute gaps -
    almost certainly a RAR-extraction artifact, not real capture order, so
    they are NOT used for grouping). Instead, an all-pairs perceptual-hash
    (dHash, Hamming distance <= 2) connected-components clustering is used
    per class to find genuine near-duplicate groups regardless of file
    order. Groups (not individual images) are then assigned to
    train/val/test with a seeded, greedy, per-class-balanced assignment
    targeting ~70/15/15.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET1_ROOT = REPO_ROOT / "_thermal_audit_ds1" / "Induction Motor-Thermal Images"
DATASET2_ROOT = REPO_ROOT / "_thermal_audit_ds2" / "IR-Motor-bmp"
MANIFEST_DIR = REPO_ROOT / "data" / "manifests"

SEED = 42
DHASH_SIZE = 8
DS2_NEAR_DUP_THRESHOLD = 2  # conservative "near-exact duplicate" cutoff, see report
DS1_TRAIN_FRAC = 0.70
DS1_VAL_FRAC = 0.15
DS1_BOUNDARY_BUFFER = 2  # images dropped at each chronological cut point

DATASET1_LABEL_MEANING = {
    "HFL": "Healthy / Full Load",
    "HML": "Healthy / Medium Load",
    "HNL": "Healthy / No Load",
    "CFL": "Corroded Bearing / Full Load",
    "CML": "Corroded Bearing / Medium Load",
    "CNL": "Corroded Bearing / No Load",
}

DATASET2_LABEL_MEANING = {
    "Noload": "Healthy, no load",
    "Rotor-0": "Stuck-rotor fault",
    "Fan": "Cooling-fan failure",
    "A50": "Stator short-circuit, phase A, 50% severity",
    "A&B50": "Stator short-circuit, phases A+B, 50% severity",
    "A30": "Stator short-circuit, phase A, 30% severity",
    "A&C30": "Stator short-circuit, phases A+C, 30% severity",
    "A&C&B30": "Stator short-circuit, all 3 phases, 30% severity",
    "A10": "Stator short-circuit, phase A, 10% severity",
    "A&C10": "Stator short-circuit, phases A+C, 10% severity",
    "A&C&B10": "Stator short-circuit, all 3 phases, 10% severity",
}

TIMESTAMP_PATTERN = re.compile(rb"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")


@dataclass
class ImageRecord:
    dataset: str
    image_path: str
    split: str | None
    klass: str
    group_id: str
    source_metadata: dict = field(default_factory=dict)


def dhash(path: Path, hash_size: int = DHASH_SIZE) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    return (resized[:, 1:] > resized[:, :-1]).flatten()


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def extract_embedded_timestamp(path: Path) -> datetime | None:
    data = path.read_bytes()
    match = TIMESTAMP_PATTERN.search(data)
    if not match:
        return None
    y, mo, da, h, mi, s = (int(x) for x in match.groups())
    try:
        return datetime(y, mo, da, h, mi, s)
    except ValueError:
        return None


class UnionFind:
    def __init__(self, items: list[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def repair_cross_split_leaks(records: list[ImageRecord], threshold: int) -> tuple[list[ImageRecord], int]:
    """After an initial split assignment, verify no validation/test image is a
    near-duplicate (by dHash) of any training image in the same class, AND no
    validation image is a near-duplicate of any test image - demoting the
    offending image to excluded (split=None) rather than silently keeping it.
    This makes the leakage guarantee actual (independently re-verified), not
    just intended by construction."""
    hashes = {r.image_path: dhash(Path(r.image_path)) for r in records}
    by_class: dict[str, list[ImageRecord]] = {}
    for r in records:
        by_class.setdefault(r.klass, []).append(r)

    demoted = 0
    for klass, klass_records in by_class.items():
        # Pass 1: validation/test vs train
        train_hashes = [hashes[r.image_path] for r in klass_records if r.split == "train"]
        for r in klass_records:
            if r.split not in ("validation", "test"):
                continue
            h = hashes[r.image_path]
            if any(hamming(h, th) <= threshold for th in train_hashes):
                r.split = None
                r.group_id = f"{r.group_id}_leak_repaired"
                demoted += 1

        # Pass 2: validation vs test (demote the validation side by convention,
        # keeping test as the more protected final held-out set)
        test_hashes = [hashes[r.image_path] for r in klass_records if r.split == "test"]
        for r in klass_records:
            if r.split != "validation":
                continue
            h = hashes[r.image_path]
            if any(hamming(h, th) <= threshold for th in test_hashes):
                r.split = None
                r.group_id = f"{r.group_id}_leak_repaired"
                demoted += 1
    return records, demoted


def build_dataset1_records() -> list[ImageRecord]:
    if not DATASET1_ROOT.is_dir():
        raise FileNotFoundError(f"Dataset 1 not found at {DATASET1_ROOT}")

    records: list[ImageRecord] = []
    for klass_dir in sorted(p for p in DATASET1_ROOT.iterdir() if p.is_dir()):
        klass = klass_dir.name
        files = sorted(klass_dir.glob("*.jpg"))
        timestamped = []
        for f in files:
            ts = extract_embedded_timestamp(f)
            timestamped.append((f, ts))

        missing = [f for f, ts in timestamped if ts is None]
        if missing:
            raise ValueError(
                f"{len(missing)} file(s) in {klass} had no embedded timestamp - "
                "chronological splitting requires it for every file."
            )

        timestamped.sort(key=lambda pair: pair[1])
        n = len(timestamped)
        n_train = round(n * DS1_TRAIN_FRAC)
        n_val = round(n * DS1_VAL_FRAC)

        train_end = n_train
        val_start = min(train_end + DS1_BOUNDARY_BUFFER, n)
        val_end = min(val_start + n_val, n)
        test_start = min(val_end + DS1_BOUNDARY_BUFFER, n)

        for i, (f, ts) in enumerate(timestamped):
            if i < train_end:
                split = "train"
            elif val_start <= i < val_end:
                split = "validation"
            elif i >= test_start:
                split = "test"
            else:
                split = None  # boundary buffer - excluded from all splits

            records.append(
                ImageRecord(
                    dataset="induction_motor_thermal_images",
                    image_path=str(f),
                    split=split,
                    klass=klass,
                    group_id=f"{klass}_chrono_block_{split or 'buffer'}",
                    source_metadata={
                        "label_meaning": DATASET1_LABEL_MEANING.get(klass, "unknown"),
                        "embedded_timestamp": ts.isoformat(),
                        "chronological_index_in_class": i,
                        "class_size": n,
                    },
                )
            )
    return records


def build_dataset2_records(rng: random.Random) -> list[ImageRecord]:
    if not DATASET2_ROOT.is_dir():
        raise FileNotFoundError(f"Dataset 2 not found at {DATASET2_ROOT}")

    records: list[ImageRecord] = []
    for klass_dir in sorted(p for p in DATASET2_ROOT.iterdir() if p.is_dir()):
        klass = klass_dir.name
        files = sorted(klass_dir.glob("*.bmp"))
        keys = [str(f) for f in files]
        hashes = {str(f): dhash(f) for f in files}

        uf = UnionFind(keys)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if hamming(hashes[keys[i]], hashes[keys[j]]) <= DS2_NEAR_DUP_THRESHOLD:
                    uf.union(keys[i], keys[j])

        groups: dict[str, list[str]] = {}
        for k in keys:
            groups.setdefault(uf.find(k), []).append(k)

        group_ids = list(groups.keys())
        rng.shuffle(group_ids)  # seeded, deterministic given SEED

        target = {"train": DS1_TRAIN_FRAC, "validation": DS1_VAL_FRAC, "test": 1 - DS1_TRAIN_FRAC - DS1_VAL_FRAC}
        counts = {"train": 0, "validation": 0, "test": 0}
        total = len(keys)
        assignment: dict[str, str] = {}

        for gid in group_ids:
            deficits = {
                split: target[split] * total - counts[split] for split in ("train", "validation", "test")
            }
            chosen = max(deficits, key=lambda s: deficits[s])
            assignment[gid] = chosen
            counts[chosen] += len(groups[gid])

        for gid, members in groups.items():
            split = assignment[gid]
            group_label = f"{klass}_neardup_group_{gid.replace(str(DATASET2_ROOT), '').strip('/\\\\')}"
            for path in members:
                records.append(
                    ImageRecord(
                        dataset="ir_motor_bmp",
                        image_path=path,
                        split=split,
                        klass=klass,
                        group_id=group_label,
                        source_metadata={
                            "label_meaning": DATASET2_LABEL_MEANING.get(klass, "unknown"),
                            "near_dup_group_size": len(members),
                        },
                    )
                )
    return records


def write_manifest(records: list[ImageRecord], path: Path, seed: int, methodology: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "seed": seed,
        "methodology": methodology,
        "record_count": len(records),
        "records": [
            {
                "dataset": r.dataset,
                "image_path": r.image_path,
                "split": r.split,
                "class": r.klass,
                "group_id": r.group_id,
                "source_metadata": r.source_metadata,
            }
            for r in records
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_class_distribution(records: list[ImageRecord], classes: list[str]) -> None:
    splits = ["train", "validation", "test", None]
    header = " | ".join(["split"] + classes + ["total"])
    print(header)
    for split in splits:
        row = [str(split)]
        rowtotal = 0
        for klass in classes:
            n = sum(1 for r in records if r.klass == klass and r.split == split)
            rowtotal += n
            row.append(str(n))
        row.append(str(rowtotal))
        print(" | ".join(row))


def main() -> None:
    rng = random.Random(SEED)

    print("=== Dataset 1: Induction Motor-Thermal Images ===")
    ds1_records = build_dataset1_records()
    ds1_records, demoted = repair_cross_split_leaks(ds1_records, DS2_NEAR_DUP_THRESHOLD)
    print(f"Leak-repair pass: demoted {demoted} validation/test image(s) that were "
          f"near-duplicates (dHash <= {DS2_NEAR_DUP_THRESHOLD}) of a training image "
          "in the same class - chronological blocking alone was insufficient.")
    write_manifest(
        ds1_records,
        MANIFEST_DIR / "thermal_dataset1_split.json",
        SEED,
        "Chronological per-class block split (train=earliest, val=middle, test=latest) "
        f"with a {DS1_BOUNDARY_BUFFER}-image buffer dropped at each boundary, PLUS an "
        f"explicit post-hoc leak-repair pass ({demoted} image(s) demoted to excluded) "
        "for validation/test images found to be near-duplicates of a training image "
        "despite the chronological blocking. Grouping evidence: embedded FLIR ASCII "
        "timestamps confirm each class is one continuous session; a dHash near-duplicate "
        "check found no clean similarity cutoff (similarity is not strictly monotonic "
        "with time distance), so chronological blocking was used as the primary method "
        "with hash-based leak-repair as a safety net.",
    )
    print_class_distribution(ds1_records, list(DATASET1_LABEL_MEANING.keys()))

    print("\n=== Dataset 2: IR-Motor-bmp ===")
    ds2_records = build_dataset2_records(rng)
    ds2_records, ds2_demoted = repair_cross_split_leaks(ds2_records, DS2_NEAR_DUP_THRESHOLD)
    print(f"Leak-repair pass: demoted {ds2_demoted} image(s) (expected ~0 - grouping "
          "should already prevent this by construction; this is an independent safety-net check).")
    write_manifest(
        ds2_records,
        MANIFEST_DIR / "thermal_dataset2_split.json",
        SEED,
        f"Per-class dHash near-duplicate connected-components (Hamming <= {DS2_NEAR_DUP_THRESHOLD}), "
        "groups assigned to train/validation/test via a seeded greedy per-class-balanced "
        "assignment targeting 70/15/15, PLUS the same independent leak-repair safety-net "
        f"check as Dataset 1 ({ds2_demoted} image(s) demoted). File-modification timestamps "
        "were checked and found unreliable (inconsistent with filename order, irregular "
        "gaps - likely a RAR-extraction artifact) and were NOT used for grouping.",
    )
    print_class_distribution(ds2_records, list(DATASET2_LABEL_MEANING.keys()))


if __name__ == "__main__":
    main()
