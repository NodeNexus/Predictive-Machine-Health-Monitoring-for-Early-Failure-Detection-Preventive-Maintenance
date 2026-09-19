"""Tests for scripts/prepare_thermal_splits.py.

These exercise the real thermal datasets extracted at the project root
(`_thermal_audit_ds1/`, `_thermal_audit_ds2/`) - not synthetic fixtures,
since the whole point is verifying leakage properties of the actual data.
All tests skip gracefully if that staging data isn't present in a given
environment (it is gitignored, large, downloaded separately).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import prepare_thermal_splits as pts  # noqa: E402

DS1_AVAILABLE = pts.DATASET1_ROOT.is_dir()
DS2_AVAILABLE = pts.DATASET2_ROOT.is_dir()

pytestmark = pytest.mark.skipif(
    not (DS1_AVAILABLE and DS2_AVAILABLE),
    reason="Thermal dataset staging folders (_thermal_audit_ds1/ds2) not present in this environment",
)


@pytest.fixture(scope="module")
def ds1_records():
    records = pts.build_dataset1_records()
    records, _ = pts.repair_cross_split_leaks(records, pts.DS2_NEAR_DUP_THRESHOLD)
    return records


@pytest.fixture(scope="module")
def ds2_records():
    import random

    rng = random.Random(pts.SEED)
    records = pts.build_dataset2_records(rng)
    records, _ = pts.repair_cross_split_leaks(records, pts.DS2_NEAR_DUP_THRESHOLD)
    return records


def _cross_split_pairs(records, threshold):
    by_split = {"train": [], "validation": [], "test": []}
    for r in records:
        if r.split in by_split:
            by_split[r.split].append(r)
    hashes = {r.image_path: pts.dhash(Path(r.image_path)) for r in records if r.split}

    violations = []
    for cls in {r.klass for r in records}:
        for sa, sb in [("train", "validation"), ("train", "test"), ("validation", "test")]:
            a_imgs = [r.image_path for r in by_split[sa] if r.klass == cls]
            b_imgs = [r.image_path for r in by_split[sb] if r.klass == cls]
            for a in a_imgs:
                for b in b_imgs:
                    if pts.hamming(hashes[a], hashes[b]) <= threshold:
                        violations.append((cls, sa, a, sb, b))
    return violations


def test_dataset1_split_is_deterministic():
    r1 = pts.build_dataset1_records()
    r1, _ = pts.repair_cross_split_leaks(r1, pts.DS2_NEAR_DUP_THRESHOLD)
    r2 = pts.build_dataset1_records()
    r2, _ = pts.repair_cross_split_leaks(r2, pts.DS2_NEAR_DUP_THRESHOLD)

    key = lambda recs: sorted((r.image_path, r.split) for r in recs)  # noqa: E731
    assert key(r1) == key(r2)


def test_dataset2_split_is_deterministic():
    import random

    r1 = pts.build_dataset2_records(random.Random(pts.SEED))
    r1, _ = pts.repair_cross_split_leaks(r1, pts.DS2_NEAR_DUP_THRESHOLD)
    r2 = pts.build_dataset2_records(random.Random(pts.SEED))
    r2, _ = pts.repair_cross_split_leaks(r2, pts.DS2_NEAR_DUP_THRESHOLD)

    key = lambda recs: sorted((r.image_path, r.split) for r in recs)  # noqa: E731
    assert key(r1) == key(r2)


def test_dataset1_no_exact_duplicate_across_splits(ds1_records):
    hashes: dict[str, set[str]] = {}
    for r in ds1_records:
        if r.split is None:
            continue
        md5 = hashlib.md5(Path(r.image_path).read_bytes()).hexdigest()
        hashes.setdefault(md5, set()).add(r.split)
    cross = [h for h, splits in hashes.items() if len(splits) > 1]
    assert cross == []


def test_dataset2_no_exact_duplicate_across_splits(ds2_records):
    hashes: dict[str, set[str]] = {}
    for r in ds2_records:
        if r.split is None:
            continue
        md5 = hashlib.md5(Path(r.image_path).read_bytes()).hexdigest()
        hashes.setdefault(md5, set()).add(r.split)
    cross = [h for h, splits in hashes.items() if len(splits) > 1]
    assert cross == []


def test_dataset1_no_near_duplicate_across_splits(ds1_records):
    violations = _cross_split_pairs(ds1_records, pts.DS2_NEAR_DUP_THRESHOLD)
    assert violations == [], f"{len(violations)} near-duplicate cross-split pair(s) found"


def test_dataset2_no_near_duplicate_across_splits(ds2_records):
    violations = _cross_split_pairs(ds2_records, pts.DS2_NEAR_DUP_THRESHOLD)
    assert violations == [], f"{len(violations)} near-duplicate cross-split pair(s) found"


def test_dataset1_no_group_spans_multiple_splits(ds1_records):
    groups: dict[str, set[str]] = {}
    for r in ds1_records:
        groups.setdefault(r.group_id, set()).add(r.split)
    violations = {g: s for g, s in groups.items() if len(s) > 1}
    assert violations == {}


def test_dataset2_no_group_spans_multiple_splits(ds2_records):
    groups: dict[str, set[str]] = {}
    for r in ds2_records:
        groups.setdefault(r.group_id, set()).add(r.split)
    violations = {g: s for g, s in groups.items() if len(s) > 1}
    assert violations == {}


def test_dataset1_all_known_classes_present_with_correct_totals(ds1_records):
    expected_counts = {"HFL": 112, "HML": 82, "HNL": 90, "CFL": 49, "CML": 79, "CNL": 76}
    for klass, expected in expected_counts.items():
        actual = sum(1 for r in ds1_records if r.klass == klass)
        assert actual == expected, f"{klass}: expected {expected} total images, found {actual}"


def test_dataset2_all_known_classes_present_with_correct_totals(ds2_records):
    expected_counts = {
        "Noload": 25, "Rotor-0": 30, "Fan": 28, "A50": 35, "A&B50": 38,
        "A30": 37, "A&C30": 38, "A&C&B30": 42, "A10": 34, "A&C10": 31, "A&C&B10": 31,
    }
    for klass, expected in expected_counts.items():
        actual = sum(1 for r in ds2_records if r.klass == klass)
        assert actual == expected, f"{klass}: expected {expected} total images, found {actual}"


def test_dataset1_every_class_has_train_and_test_representation(ds1_records):
    for klass in {"HFL", "HML", "HNL", "CFL", "CML", "CNL"}:
        train_n = sum(1 for r in ds1_records if r.klass == klass and r.split == "train")
        test_n = sum(1 for r in ds1_records if r.klass == klass and r.split == "test")
        assert train_n > 0, f"{klass} has no training images"
        assert test_n > 0, f"{klass} has no test images"


def test_dataset2_flags_classes_with_zero_validation_or_test(ds2_records):
    """Documents the known, honest limitation rather than hiding it: some
    Dataset 2 classes collapse into one giant near-duplicate group and get
    zero validation and/or test representation. This test asserts the
    *known* set of affected classes so a future re-run alerts us if the
    situation changes (improves or gets worse) rather than passing silently."""
    starved = set()
    for klass in {
        "Noload", "Rotor-0", "Fan", "A50", "A&B50", "A30", "A&C30",
        "A&C&B30", "A10", "A&C10", "A&C&B10",
    }:
        val_n = sum(1 for r in ds2_records if r.klass == klass and r.split == "validation")
        test_n = sum(1 for r in ds2_records if r.klass == klass and r.split == "test")
        if val_n == 0 or test_n == 0:
            starved.add(klass)

    known_starved = {"A30", "A&C30", "A10", "A&C10"}
    assert starved == known_starved, (
        f"Set of validation/test-starved classes changed: {starved} vs expected {known_starved} - "
        "re-check docs/THERMAL_SPLIT_REPORT.md, this may be an improvement or a regression."
    )


def test_manifest_files_are_valid_json_with_required_fields():
    for path in [
        pts.MANIFEST_DIR / "thermal_dataset1_split.json",
        pts.MANIFEST_DIR / "thermal_dataset2_split.json",
    ]:
        assert path.is_file(), f"Manifest not found: {path} - run scripts/prepare_thermal_splits.py first"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "seed" in data and "methodology" in data and "records" in data
        assert data["seed"] == pts.SEED
        for record in data["records"]:
            for field in ("dataset", "image_path", "split", "class", "group_id"):
                assert field in record
            assert record["split"] in ("train", "validation", "test", None)
            assert Path(record["image_path"]).is_file(), f"Missing image referenced in manifest: {record['image_path']}"


def test_missing_image_raises_clear_error(tmp_path):
    fake_path = tmp_path / "does_not_exist.jpg"
    with pytest.raises(ValueError):
        pts.dhash(fake_path)


def test_missing_timestamp_raises_clear_error(tmp_path):
    fake_jpg = tmp_path / "no_timestamp.jpg"
    fake_jpg.write_bytes(b"not a real jpeg, no embedded timestamp here")
    assert pts.extract_embedded_timestamp(fake_jpg) is None
