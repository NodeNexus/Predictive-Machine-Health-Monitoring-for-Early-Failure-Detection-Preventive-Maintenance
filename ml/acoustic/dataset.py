"""Feature extraction and leak-safe split construction for Acoustic ML V1
(DATASET/bearing/bearing).

DATASET AUDIT FINDING (see data/manifests/acoustic_dataset_audit.json,
produced by scripts/audit_acoustic_dataset.py): this is a domain-
generalization-style anomaly-detection dataset (DCASE-Task2 layout). The
vendor's own train/ folder contains ONLY normal-label files (2999 of them,
zero anomaly examples) and every anomaly example (300 total) lives in the
vendor's test/ folder alongside 300 held-out normal files. A supervised
classifier CANNOT be trained on the vendor train/test folders as given -
vendor-train has no anomaly examples to learn from. All 3599 files (both
vendor folders) are pooled here and re-split for this supervised baseline.

SPLIT STRATEGY: stratified file-level split by (section, domain, label),
NOT full-group holdout. This is a deliberate, documented choice - the task
brief prefers held-out source/session/group splitting "if grouping
information permits it", but that only applies where multiple files could
be correlated fragments of one recording (as with the IMS vibration
timeline, where adjacent windows share physical continuity). Here, each
WAV is an independently recorded 10-second clip; the dataset audit
verified ZERO exact-duplicate file content across all 3599 files
(including across the vendor train/ and test/ folders), so there is no
evidence of shared-session leakage at the file level. The real nuisance
variables are `section` (3 distinct machine/bearing units) and `domain`
(source vs. target recording condition, with a different velocity range
per domain) - stratifying by (section, domain, label) guarantees every
split sees every section, every domain, and both classes, which is the
right leak-guard for THIS dataset's actual risk (label imbalance and
per-section/per-domain distribution shift), not a session-continuity risk
that doesn't exist here.
"""
from __future__ import annotations

import json
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "DATASET" / "bearing" / "bearing"
INVENTORY_PATH = REPO_ROOT / "data" / "manifests" / "acoustic_dataset_inventory.json"
SPLIT_MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "acoustic_ml_v1_split.json"

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
SPLIT_SEED = 42

OCTAVE_BAND_CENTERS_HZ = [15.625, 31.25, 62.5, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0]
THIRD_OCTAVE_BAND_CENTERS_HZ = [
    19.7, 24.8, 31.2, 39.4, 49.6, 62.5, 78.7, 99.2, 125.0, 157.5, 198.4, 250.0, 315.0, 396.9,
    500.0, 630.0, 793.7, 1000.0, 1259.9, 1587.4, 2000.0, 2519.8, 3174.8, 4000.0, 5039.7, 6349.6, 8000.0,
]

FEATURE_COLUMNS = (
    ["rms", "peak_amplitude", "crest_factor", "energy"]
    + ["dominant_frequency", "spectral_centroid", "spectral_bandwidth", "spectral_rolloff", "spectral_flatness"]
    + ["top_spectral_peak_frequency", "top_spectral_peak_magnitude"]
    + [f"octave_band_{i}" for i in range(len(OCTAVE_BAND_CENTERS_HZ))]
    + [f"third_octave_band_{i}" for i in range(len(THIRD_OCTAVE_BAND_CENTERS_HZ))]
    + [f"mfcc_{i}" for i in range(13)]
)

FEATURE_FAMILY_OF = {}
for _c in ["rms", "peak_amplitude", "crest_factor", "energy"]:
    FEATURE_FAMILY_OF[_c] = "temporal"
for _c in [
    "dominant_frequency", "spectral_centroid", "spectral_bandwidth", "spectral_rolloff", "spectral_flatness",
    "top_spectral_peak_frequency", "top_spectral_peak_magnitude",
]:
    FEATURE_FAMILY_OF[_c] = "spectral"
for i in range(len(OCTAVE_BAND_CENTERS_HZ)):
    FEATURE_FAMILY_OF[f"octave_band_{i}"] = "octave"
for i in range(len(THIRD_OCTAVE_BAND_CENTERS_HZ)):
    FEATURE_FAMILY_OF[f"third_octave_band_{i}"] = "third_octave"
for i in range(13):
    FEATURE_FAMILY_OF[f"mfcc_{i}"] = "mfcc"


def load_inventory() -> list[dict]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))["records"]


def load_waveform(relative_file: str) -> np.ndarray:
    """Loads a full 10-second clip, normalized to [-1, 1] - the same
    convention app.pipelines.acoustic.readers.AudioFileReader uses for
    16-bit PCM. One WAV file = one unit of analysis (matches the label
    granularity: the dataset labels whole clips, not sub-windows)."""
    path = DATASET_DIR / relative_file
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return data


def extract_features_for_record(record: dict, sample_rate: float = 16000.0) -> dict:
    """Reuses app.pipelines.acoustic.features.extract_acoustic_features
    (the existing, already-validated acoustic pipeline) twice - once per
    band_type - rather than re-implementing spectral analysis. No parallel
    feature-extraction implementation is introduced."""
    import sys

    backend_root = REPO_ROOT / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from app.pipelines.acoustic.features import extract_acoustic_features

    window = load_waveform(record["file"])
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


def build_split(records: list[dict]) -> list[dict]:
    """Stratified file-level split by (section, domain, label) - see this
    module's docstring for why this is the right leak-guard here, rather
    than full-group holdout."""
    rng = np.random.default_rng(SPLIT_SEED)

    strata: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        strata[(r["section"], r["domain"], r["label"])].append(i)

    split_of: dict[int, str] = {}
    for key, indices in strata.items():
        indices = list(indices)
        rng.shuffle(indices)
        m = len(indices)
        train_end = round(m * TRAIN_FRAC)
        val_end = train_end + round(m * VAL_FRAC)
        for j, idx in enumerate(indices):
            if j < train_end:
                split_of[idx] = "train"
            elif j < val_end:
                split_of[idx] = "validation"
            else:
                split_of[idx] = "test"

    result = []
    for i, r in enumerate(records):
        result.append({**r, "split": split_of[i]})
    return result


def build_feature_matrix(records: list[dict], feature_columns: list[str] = FEATURE_COLUMNS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    label_to_idx = {"normal": 0, "anomaly": 1}
    X = np.array([[r["features"][col] for col in feature_columns] for r in records], dtype=np.float64)
    y = np.array([label_to_idx[r["label"]] for r in records], dtype=np.int64)
    groups = np.array([f"{r['section']}|{r['domain']}" for r in records])
    return X, y, groups


def load_split_manifest(path: Path = SPLIT_MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def records_for_split(manifest: dict, split: str) -> list[dict]:
    return [r for r in manifest["records"] if r["split"] == split]
