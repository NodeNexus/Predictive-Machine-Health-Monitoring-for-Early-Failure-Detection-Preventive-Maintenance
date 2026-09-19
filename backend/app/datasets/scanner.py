"""Dataset inspection/scanning.

Produces a machine-readable manifest by actually reading file headers and
directory contents - it never guesses metadata that isn't present in the
files themselves. Two label filename conventions were observed by manual
inspection and are both handled:

  DCASE-style:  section_00_source_test_anomaly_0000_vel_6.wav
  MIMII-style:  anomaly_id_00_00000000.wav

Adding a new acoustic dataset that follows one of these two conventions
requires no code change - just point `ACOUSTIC_DATASETS` at its directory.
"""
from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.datasets.manifest import DatasetManifestEntry

logger = get_logger("dataset_scanner")

_LABEL_RE = re.compile(r"(?:^|_)(normal|anomaly)(?:_|\.|$)")


@dataclass
class AcousticDatasetSpec:
    dataset_name: str
    machine_type: str
    root: Path  # directory directly containing train/ and test/


ACOUSTIC_DATASETS = [
    AcousticDatasetSpec("bearing", "bearing", Path("bearing/bearing")),
    AcousticDatasetSpec("fan", "fan", Path("fan/fan")),
    AcousticDatasetSpec("valve", "valve", Path("valve/valve")),
    AcousticDatasetSpec("gearbox", "gearbox", Path("gearbox/gearbox")),
    AcousticDatasetSpec("dev_data_pump", "pump", Path("dev_data_pump/pump")),
]


def _label_from_filename(name: str) -> str | None:
    match = _LABEL_RE.search(name)
    return match.group(1) if match else None


def _read_wav_header(path: Path) -> tuple[int, int, int] | None:
    """Returns (channels, sample_rate, n_frames), or None if unreadable."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnchannels(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError, OSError) as exc:
        logger.warning(f"Could not read WAV header for {path}: {exc}")
        return None


def scan_acoustic_dataset(spec: AcousticDatasetSpec, dataset_dir: Path) -> DatasetManifestEntry | None:
    root = dataset_dir / spec.root
    if not root.is_dir():
        logger.warning(f"Acoustic dataset root not found: {root}")
        return None

    wav_files: list[Path] = []
    for subset in ("train", "test"):
        subset_dir = root / subset
        if subset_dir.is_dir():
            wav_files.extend(sorted(subset_dir.glob("*.wav")))

    if not wav_files:
        logger.warning(f"No WAV files found under {root}")
        return None

    normal_count = 0
    anomaly_count = 0
    unlabeled_count = 0
    for f in wav_files:
        label = _label_from_filename(f.name)
        if label == "normal":
            normal_count += 1
        elif label == "anomaly":
            anomaly_count += 1
        else:
            unlabeled_count += 1

    # Sample header info from the first readable file rather than assuming
    # uniformity; note in `notes` if a later file disagrees.
    sample_rate: int | None = None
    channels: int | None = None
    total_duration = 0.0
    duration_mismatch = False
    for f in wav_files:
        header = _read_wav_header(f)
        if header is None:
            continue
        ch, sr, n = header
        duration = n / sr if sr else 0.0
        total_duration += duration
        if sample_rate is None:
            sample_rate, channels = sr, ch
        elif sr != sample_rate or ch != channels:
            duration_mismatch = True

    notes = None
    if unlabeled_count:
        notes = f"{unlabeled_count} file(s) did not match the normal/anomaly filename convention."
    if duration_mismatch:
        mismatch_note = "Not all files share the same sample rate/channel count."
        notes = f"{notes} {mismatch_note}" if notes else mismatch_note

    return DatasetManifestEntry(
        dataset_name=spec.dataset_name,
        machine_type=spec.machine_type,
        modality="acoustic",
        path=str(root),
        format="wav",
        sample_count=len(wav_files),
        duration_seconds=round(total_duration, 1),
        sample_rate=sample_rate,
        channels=channels,
        label_categories=["normal", "anomaly"] if (normal_count or anomaly_count) else [],
        normal_count=normal_count or None,
        anomaly_count=anomaly_count or None,
        notes=notes,
    )


# --- Vibration: IMS bearing run-to-failure dataset -------------------------
#
# Per the vendor README (DATASET/IMS/IMS/Readme Document for IMS Bearing
# Data.pdf): 20 kHz sample rate, 20,480 points/file (~1.024s snapshot), no
# per-file normal/anomaly label - only "failure occurred by the end of the
# test" is documented. We therefore do NOT invent a label_categories list
# for this dataset; it is degradation/run-to-failure data, not a labelled
# anomaly-detection dataset.
IMS_SAMPLE_RATE = 20000
IMS_POINTS_PER_FILE = 20480

IMS_TEST_SETS = [
    # (subdir relative to DATASET/IMS/IMS, folder actually containing the
    # per-timestamp files, expected channel count, description, expected
    # file count per the vendor README - note set 3's rar extracts to
    # "4th_test", a known quirk of the original archive, not a 4th dataset).
    ("1st_test", Path("1st_test/1st_test"), 8, "Set 1: inner race defect (bearing 3), roller element defect (bearing 4).", 2156),
    ("2nd_test", Path("2nd_test/2nd_test"), 4, "Set 2: outer race failure (bearing 1).", 984),
    ("3rd_test", Path("3rd_test/4th_test/txt"), 4, "Set 3: outer race failure (bearing 3). NOTE: archive folder is named '4th_test' internally.", 4448),
]


def scan_ims_vibration(dataset_dir: Path) -> list[DatasetManifestEntry]:
    root = dataset_dir / "IMS" / "IMS"
    entries: list[DatasetManifestEntry] = []
    for name, subpath, expected_channels, description, expected_file_count in IMS_TEST_SETS:
        test_dir = root / subpath
        if not test_dir.is_dir():
            logger.warning(f"IMS test set not found: {test_dir}")
            continue

        files = sorted(p for p in test_dir.iterdir() if p.is_file())
        if not files:
            continue

        actual_channels: int | None = None
        try:
            with files[0].open() as fh:
                first_line = fh.readline()
            actual_channels = len(first_line.strip().split("\t"))
        except OSError as exc:
            logger.warning(f"Could not read {files[0]}: {exc}")

        notes = description
        if actual_channels is not None and actual_channels != expected_channels:
            notes += f" WARNING: observed {actual_channels} channels, expected {expected_channels}."
        if len(files) != expected_file_count:
            notes += (
                f" WARNING: observed {len(files)} files, README states {expected_file_count} "
                "- discrepancy not resolved, treat file count as the actually-observed value."
            )

        entries.append(
            DatasetManifestEntry(
                dataset_name=f"IMS_{name}",
                machine_type="bearing",
                modality="vibration",
                path=str(test_dir),
                format="ascii_tsv",
                sample_count=len(files),
                duration_seconds=round(len(files) * IMS_POINTS_PER_FILE / IMS_SAMPLE_RATE, 1),
                sample_rate=IMS_SAMPLE_RATE,
                channels=actual_channels,
                label_categories=[],  # run-to-failure, not per-file labelled
                notes=notes,
            )
        )
    return entries


# --- Thermal: demo videos ---------------------------------------------------

def scan_thermal_videos(video_dir: Path) -> list[DatasetManifestEntry]:
    import cv2  # local import: only needed here, keeps module import light

    entries: list[DatasetManifestEntry] = []
    for f in sorted(video_dir.glob("*.mp4")):
        cap = cv2.VideoCapture(str(f))
        if not cap.isOpened():
            logger.warning(f"Could not open video: {f}")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        duration = frame_count / fps if fps else None

        entries.append(
            DatasetManifestEntry(
                dataset_name=f.stem,
                machine_type=None,
                modality="thermal",
                path=str(f),
                format="mp4",
                sample_count=frame_count,
                duration_seconds=round(duration, 1) if duration else None,
                sample_rate=round(fps, 2) if fps else None,  # frames/sec, not audio
                channels=None,
                label_categories=[],
                notes=(
                    f"{width}x{height} visible-light recording of a thermal-camera display; "
                    "NOT calibrated radiometric temperature data unless proven otherwise."
                ),
            )
        )
    return entries


def scan_all(dataset_dir: Path, video_dir: Path) -> list[DatasetManifestEntry]:
    entries: list[DatasetManifestEntry] = []

    for spec in ACOUSTIC_DATASETS:
        entry = scan_acoustic_dataset(spec, dataset_dir)
        if entry:
            entries.append(entry)

    entries.extend(scan_ims_vibration(dataset_dir))
    entries.extend(scan_thermal_videos(video_dir))

    return entries
