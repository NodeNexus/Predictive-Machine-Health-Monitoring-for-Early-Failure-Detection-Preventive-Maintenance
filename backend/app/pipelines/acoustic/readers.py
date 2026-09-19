"""Audio sample sources.

AudioFileReader (demo) and LiveMicrophone (live) both implement
AudioInput. WAV files are streamed via the stdlib `wave` module in
fixed-size blocks rather than loaded whole, matching the streaming design
used by the other modalities.
"""
from __future__ import annotations

import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.pipelines.common.interfaces import AudioInput, SampleChunk

_DTYPE_BY_SAMPWIDTH = {1: np.uint8, 2: np.int16, 4: np.int32}


class AudioFileReader(AudioInput):
    """Streams samples from a WAV file (DEMO MODE).

    Multi-channel files are downmixed to mono by averaging channels, since
    the analyzer pipeline operates on a single 1-D signal.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._wav: wave.Wave_read | None = None
        self._sample_rate: float = 0.0
        self._channels = 1
        self._sampwidth = 2

    def open(self) -> None:
        if not self._path.is_file():
            raise FileNotFoundError(f"Audio file not found: {self._path}")
        self._wav = wave.open(str(self._path), "rb")
        self._sample_rate = float(self._wav.getframerate())
        self._channels = self._wav.getnchannels()
        self._sampwidth = self._wav.getsampwidth()
        if self._sampwidth not in _DTYPE_BY_SAMPWIDTH:
            raise ValueError(f"Unsupported WAV sample width: {self._sampwidth} bytes ({self._path})")

    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        if self._wav is None:
            raise RuntimeError("AudioFileReader.open() must be called first")

        raw = self._wav.readframes(max_samples)
        if not raw:
            return None

        dtype = _DTYPE_BY_SAMPWIDTH[self._sampwidth]
        data = np.frombuffer(raw, dtype=dtype).astype(np.float64)
        if self._channels > 1:
            data = data.reshape(-1, self._channels).mean(axis=1)

        # Normalize to [-1, 1] using the dtype's full range, so features
        # are comparable across different bit depths.
        max_val = float(np.iinfo(dtype).max) if dtype != np.uint8 else 127.5
        offset = 128.0 if dtype == np.uint8 else 0.0
        normalized = (data - offset) / max_val

        return SampleChunk(
            samples=normalized,
            sample_rate=self._sample_rate,
            timestamp=datetime.now(timezone.utc),
            metadata={"source_file": str(self._path), "original_channels": self._channels},
        )

    def close(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    @property
    def sample_rate(self) -> float:
        return self._sample_rate

    @property
    def is_live(self) -> bool:
        return False

    @property
    def source_description(self) -> str:
        return f"demo:{self._path}"


class LiveMicrophone(AudioInput):
    """Live microphone input.

    No audio-capture backend (e.g. `sounddevice`/`pyaudio`) is wired up
    yet - `open()` honestly raises rather than fabricating a connected
    microphone. Swapping in a real backend later requires no change to
    this class's interface or any downstream analyzer code.
    """

    def __init__(self, device_id: str, sample_rate: float = 16000.0) -> None:
        self._device_id = device_id
        self._sample_rate = sample_rate

    def open(self) -> None:
        raise ConnectionError(f"Microphone not connected (no audio backend configured for '{self._device_id}')")

    def read_chunk(self, max_samples: int) -> SampleChunk | None:
        raise RuntimeError("LiveMicrophone has no backend connected")

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
        return f"live:microphone({self._device_id})"
