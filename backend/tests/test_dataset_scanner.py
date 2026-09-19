import wave
from pathlib import Path

import pytest

from app.core.config import settings
from app.datasets.scanner import (
    AcousticDatasetSpec,
    _label_from_filename,
    scan_acoustic_dataset,
    scan_all,
)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("section_00_source_test_anomaly_0000_vel_6.wav", "anomaly"),
        ("section_00_source_train_normal_0000_vel_22.wav", "normal"),
        ("anomaly_id_00_00000000.wav", "anomaly"),
        ("normal_id_00_00000000.wav", "normal"),
        ("attributes_00.csv", None),
    ],
)
def test_label_from_filename(filename, expected):
    assert _label_from_filename(filename) == expected


def _write_silent_wav(path: Path, n_frames: int = 1600, sample_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n_frames)


def test_scan_acoustic_dataset_with_synthetic_files(tmp_path: Path):
    root = tmp_path / "toy" / "toy"
    (root / "train").mkdir(parents=True)
    (root / "test").mkdir(parents=True)

    for i in range(3):
        _write_silent_wav(root / "train" / f"section_00_source_train_normal_{i:04d}.wav")
    for i, label in enumerate(["normal", "anomaly", "anomaly"]):
        _write_silent_wav(root / "test" / f"section_00_source_test_{label}_{i:04d}.wav")

    spec = AcousticDatasetSpec("toy", "toy_machine", Path("toy/toy"))
    entry = scan_acoustic_dataset(spec, tmp_path)

    assert entry is not None
    assert entry.sample_count == 6
    assert entry.normal_count == 4
    assert entry.anomaly_count == 2
    assert entry.sample_rate == 16000
    assert entry.channels == 1


def test_scan_acoustic_dataset_missing_dir_returns_none(tmp_path: Path):
    spec = AcousticDatasetSpec("missing", "x", Path("does/not/exist"))
    assert scan_acoustic_dataset(spec, tmp_path) is None


@pytest.mark.skipif(not settings.dataset_dir.is_dir(), reason="DATASET/ not present in this environment")
def test_scan_all_against_real_dataset_directory():
    entries = scan_all(settings.dataset_dir, settings.video_dir)
    assert len(entries) > 0
    modalities = {e.modality for e in entries}
    assert modalities <= {"acoustic", "vibration", "thermal", "other"}
    # every entry must report where it actually came from
    assert all(e.path for e in entries)
