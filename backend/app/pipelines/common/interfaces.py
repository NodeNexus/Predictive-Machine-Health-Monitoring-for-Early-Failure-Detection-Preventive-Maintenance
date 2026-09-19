"""Input abstractions shared by DEMO MODE and LIVE MODE.

The core processing engine (thermal/vibration/acoustic analyzers) only ever
talks to these interfaces. It has no knowledge of whether data originates
from an MP4 file, a WAV file, a CSV dataset, a USB camera, an RTSP stream,
a DAQ card, or a microcontroller. Only the concrete adapter changes; the
downstream analyzers, fusion engine, and dashboard payloads are identical
between demo and live deployments.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ThermalFrame:
    frame_index: int
    timestamp: datetime
    image: np.ndarray  # HxW (grayscale intensity) or HxWx3 (colorized/visible palette)
    is_radiometric: bool = False  # True only if pixel values are calibrated temperatures
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SampleChunk:
    """A block of raw 1-D samples, used by both vibration and audio inputs."""

    samples: np.ndarray
    sample_rate: float
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class ThermalInput(ABC):
    """Abstract source of thermal frames (video file, live camera, etc.)."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read_frame(self) -> ThermalFrame | None:
        """Return the next frame, or None when the stream/file is exhausted."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def source_description(self) -> str:
        """Human-readable provenance, e.g. 'demo:VIDEO/engine.mp4' or 'live:FLIR Lepton (usb:0)'."""

    def __enter__(self) -> "ThermalInput":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class VibrationInput(ABC):
    """Abstract source of raw vibration samples (dataset file, live DAQ/sensor)."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        """Return up to max_samples new samples, or None when exhausted."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def sample_rate(self) -> float: ...

    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def source_description(self) -> str: ...

    def __enter__(self) -> "VibrationInput":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class AudioInput(ABC):
    """Abstract source of raw audio samples (WAV file, live microphone)."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        """Return up to max_samples new samples, or None when exhausted."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def sample_rate(self) -> float: ...

    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def source_description(self) -> str: ...

    def __enter__(self) -> "AudioInput":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class SlidingWindowBuffer:
    """Accumulates streamed 1-D samples and yields fixed-size overlapping windows.

    Shared by the vibration and acoustic pipelines so both use identical
    streaming/window semantics regardless of input source.
    """

    def __init__(self, window_size: int, hop_size: int) -> None:
        if window_size <= 0 or hop_size <= 0:
            raise ValueError("window_size and hop_size must be positive")
        self.window_size = window_size
        self.hop_size = hop_size
        self._buffer = np.empty(0, dtype=np.float64)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        """Add new samples; return any complete windows now available."""
        self._buffer = np.concatenate([self._buffer, samples.astype(np.float64, copy=False)])
        windows: list[np.ndarray] = []
        while len(self._buffer) >= self.window_size:
            windows.append(self._buffer[: self.window_size].copy())
            self._buffer = self._buffer[self.hop_size :]
        return windows

    def flush(self) -> np.ndarray | None:
        """Return whatever is left in the buffer (may be shorter than window_size)."""
        if len(self._buffer) == 0:
            return None
        remainder = self._buffer.copy()
        self._buffer = np.empty(0, dtype=np.float64)
        return remainder
