"""Vibration sample sources.

IMSVibrationDatasetReader (demo) and LiveVibrationSensor (live) both
implement VibrationInput. Files are loaded one at a time (not the whole
test set at once) to keep memory bounded, matching the streaming design
used everywhere else.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.pipelines.common.interfaces import SampleChunk, VibrationInput

logger = get_logger("vibration.readers")


class IMSVibrationDatasetReader(VibrationInput):
    """Streams one channel of the IMS run-to-failure dataset.

    Each file on disk is a 20,480-point, tab-separated 1-second snapshot
    (see docs/history/DATASETS.md). `channel` selects which column (0-indexed) to
    stream - e.g. channel 0 = bearing 1 in the 4-channel test sets.

    `start_file`/`end_file` optionally bound playback to a sorted-file-index
    range (both inclusive, 0-indexed) - e.g. to hold a demo within a known
    stable segment, or to focus on a known-degraded segment, of an
    otherwise very long run-to-failure sequence. Default behavior (both
    None) is unchanged: stream every file in the directory, exactly as
    before this option existed.
    """

    def __init__(
        self,
        test_dir: Path | str,
        channel: int,
        sample_rate: float = 20000.0,
        start_file: int | None = None,
        end_file: int | None = None,
    ) -> None:
        self._test_dir = Path(test_dir)
        self._channel = channel
        self._sample_rate = sample_rate
        self._start_file = start_file
        self._end_file = end_file
        self._files: list[Path] = []
        self._file_index = 0
        self._buffer = np.empty(0, dtype=np.float64)

    def open(self) -> None:
        if not self._test_dir.is_dir():
            raise FileNotFoundError(f"IMS test directory not found: {self._test_dir}")
        all_files = sorted(p for p in self._test_dir.iterdir() if p.is_file())
        if not all_files:
            raise FileNotFoundError(f"No data files found in {self._test_dir}")

        start = self._start_file or 0
        end = self._end_file if self._end_file is not None else len(all_files) - 1
        if start < 0 or end >= len(all_files) or start > end:
            raise ValueError(
                f"Invalid file range [{start}, {end}] for {self._test_dir} "
                f"({len(all_files)} files available, indices 0..{len(all_files) - 1})"
            )

        self._files = all_files[start : end + 1]
        self._file_index = 0
        self._buffer = np.empty(0, dtype=np.float64)

    def _load_next_file(self) -> bool:
        if self._file_index >= len(self._files):
            return False
        path = self._files[self._file_index]
        self._file_index += 1
        data = np.loadtxt(path, dtype=np.float64)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if self._channel >= data.shape[1]:
            raise ValueError(
                f"Channel {self._channel} requested but {path.name} only has {data.shape[1]} channel(s)"
            )
        self._buffer = np.concatenate([self._buffer, data[:, self._channel]])
        return True

    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        while len(self._buffer) < max_samples:
            if not self._load_next_file():
                break
        if len(self._buffer) == 0:
            return None

        n = min(max_samples, len(self._buffer))
        samples = self._buffer[:n].copy()
        self._buffer = self._buffer[n:]

        return SampleChunk(
            samples=samples,
            sample_rate=self._sample_rate,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "test_dir": str(self._test_dir),
                "channel": self._channel,
                "files_consumed": self._file_index,
                "total_files": len(self._files),
            },
        )

    def close(self) -> None:
        self._buffer = np.empty(0, dtype=np.float64)

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    @property
    def is_live(self) -> bool:
        return False

    @property
    def source_description(self) -> str:
        range_suffix = ""
        if self._start_file is not None or self._end_file is not None:
            range_suffix = f"[{self._start_file or 0}:{self._end_file if self._end_file is not None else '-1'}]"
        return f"demo:{self._test_dir}#channel{self._channel}{range_suffix}"


class LiveVibrationSensor(VibrationInput):
    """Live accelerometer/DAQ input.

    No vendor DAQ backend is wired up yet (no hardware available during
    development) - `open()` honestly raises rather than fabricating a
    connected sensor. A real backend (e.g. NI-DAQmx, a serial protocol, or
    a vendor SDK) can be injected later via `backend_factory` without
    changing this class's interface or any downstream analyzer code.
    """

    def __init__(self, device_id: str, sample_rate: float = 20000.0) -> None:
        self._device_id = device_id
        self._sample_rate = sample_rate

    def open(self) -> None:
        raise ConnectionError(f"Vibration sensor not connected (no DAQ backend configured for '{self._device_id}')")

    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        raise RuntimeError("LiveVibrationSensor has no backend connected")

    def close(self) -> None:
        pass

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    @property
    def is_live(self) -> bool:
        return True

    @property
    def source_description(self) -> str:
        return f"live:vibration({self._device_id})"
