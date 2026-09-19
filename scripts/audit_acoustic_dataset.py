#!/usr/bin/env python
"""ACOUSTIC ML V1 - step 1: dataset audit.

Inspects every WAV file under DATASET/bearing/bearing/{train,test}: parses
the filename convention, checks sample rate/duration consistency, and
computes a content hash per file to detect exact duplicates (including
across the vendor train/ and test/ folders, which must never happen but is
checked rather than assumed).

Writes data/manifests/acoustic_dataset_audit.json.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import wave
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "DATASET" / "bearing" / "bearing"

# section_00_source_train_normal_0000_vel_22.wav
# section_01_target_test_anomaly_0000_vel_4_loc_F.wav
# section_02_target_train_normal_0000_vel_6_f-n_C.wav
NAME_RE = re.compile(
    r"^section_(?P<section>\d+)_(?P<domain>source|target)_(?P<vendor_split>train|test)_"
    r"(?P<label>normal|anomaly)_(?P<index>\d+)_vel_(?P<vel>\d+)"
    r"(?:_loc_(?P<loc>[A-Za-z]+))?(?:_f-n_(?P<fn>[A-Za-z]+))?\.wav$"
)


def parse_filename(name: str) -> dict | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    d["index"] = int(d["index"])
    d["vel"] = int(d["vel"])
    return d


def main() -> None:
    records = []
    unparsed = []
    for vendor_split_dir in ("train", "test"):
        folder = DATASET_DIR / vendor_split_dir
        for path in sorted(folder.glob("*.wav")):
            parsed = parse_filename(path.name)
            if parsed is None:
                unparsed.append(str(path.relative_to(DATASET_DIR)))
                continue
            with wave.open(str(path), "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                frame_rate = wf.getframerate()
                n_frames = wf.getnframes()
                duration = n_frames / frame_rate if frame_rate else 0.0

            content = path.read_bytes()
            content_hash = hashlib.md5(content).hexdigest()

            records.append(
                {
                    "file": str(path.relative_to(DATASET_DIR)),
                    "vendor_split": parsed["vendor_split"],  # dataset's own train/test folder - NOT our ML split
                    "section": parsed["section"],
                    "domain": parsed["domain"],
                    "label": parsed["label"],
                    "index": parsed["index"],
                    "vel": parsed["vel"],
                    "loc": parsed["loc"],
                    "fn": parsed["fn"],
                    "n_channels": n_channels,
                    "sample_width_bytes": sample_width,
                    "sample_rate": frame_rate,
                    "n_frames": n_frames,
                    "duration_seconds": duration,
                    "content_hash": content_hash,
                }
            )

    print(f"Parsed {len(records)} files, {len(unparsed)} unparsed")
    if unparsed:
        print("Unparsed filenames (first 10):", unparsed[:10])

    label_counts = Counter(r["label"] for r in records)
    domain_counts = Counter(r["domain"] for r in records)
    section_counts = Counter(r["section"] for r in records)
    vendor_split_counts = Counter(r["vendor_split"] for r in records)
    section_domain_label = Counter((r["section"], r["domain"], r["label"]) for r in records)

    sample_rates = Counter(r["sample_rate"] for r in records)
    channels = Counter(r["n_channels"] for r in records)
    widths = Counter(r["sample_width_bytes"] for r in records)
    durations = [r["duration_seconds"] for r in records]

    # duplicate content detection - across the WHOLE pool, including across
    # the vendor train/ vs test/ folders (a real leak if found).
    hash_to_files = defaultdict(list)
    for r in records:
        hash_to_files[r["content_hash"]].append(r["file"])
    duplicate_groups = {h: files for h, files in hash_to_files.items() if len(files) > 1}

    # vendor-train contains ZERO anomaly examples - critical for split design.
    vendor_train_labels = Counter(r["label"] for r in records if r["vendor_split"] == "train")

    audit = {
        "dataset_dir": str(DATASET_DIR),
        "total_files": len(records),
        "unparsed_files": unparsed,
        "label_counts": dict(label_counts),
        "domain_counts": dict(domain_counts),
        "section_counts": dict(section_counts),
        "vendor_split_counts": dict(vendor_split_counts),
        "vendor_train_label_counts": dict(vendor_train_labels),
        "section_domain_label_breakdown": {f"{s}|{d}|{l}": c for (s, d, l), c in section_domain_label.items()},
        "sample_rate_consistency": dict(sample_rates),
        "channel_consistency": dict(channels),
        "sample_width_byte_consistency": dict(widths),
        "duration_seconds": {
            "min": min(durations),
            "max": max(durations),
            "mean": sum(durations) / len(durations),
        },
        "exact_duplicate_content_groups_found": len(duplicate_groups),
        "exact_duplicate_examples": dict(list(duplicate_groups.items())[:5]),
        "critical_finding": (
            "The vendor 'train' folder contains ONLY normal-label files (zero anomaly examples) - "
            "this is a domain-generalization-style dataset layout (source domain: plentiful normal "
            "training data; target domain: a handful of normal + a held-out test set with both classes). "
            "A supervised classifier CANNOT be trained using the vendor train/test folders as-is, since "
            "vendor-train has no anomaly examples at all. All files (both vendor folders) must be pooled "
            "and re-split for this supervised baseline task."
        ),
    }

    out_path = REPO_ROOT / "data" / "manifests" / "acoustic_dataset_audit.json"
    out_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    records_path = REPO_ROOT / "data" / "manifests" / "acoustic_dataset_inventory.json"
    records_path.write_text(json.dumps({"records": records}, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in audit.items() if k not in ("exact_duplicate_examples",)}, indent=2))
    print(f"\nSaved {out_path}")
    print(f"Saved {records_path}")


if __name__ == "__main__":
    main()
