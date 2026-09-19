"""Stateful, windowed acoustic analysis."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.pipelines.acoustic.features import AcousticFeatures, extract_acoustic_features
from app.pipelines.common.interfaces import SampleChunk, SlidingWindowBuffer
from app.pipelines.common.octave import BandType


class AcousticBaseline(BaseModel):
    feature_stats: dict[str, tuple[float, float]]  # feature_name -> (mean, std)


class AcousticEvidence(BaseModel):
    window_index: int
    timestamp: datetime
    source_description: str
    features: AcousticFeatures
    baseline_deviation: dict[str, float] = {}


class AcousticAnalyzer:
    def __init__(
        self,
        sample_rate: float,
        window_seconds: float = 1.0,
        overlap: float = 0.5,
        band_type: BandType = "octave",
        n_mfcc: int = 13,
        fft_size: int = 2048,
        hop_length: int = 512,
        baseline: AcousticBaseline | None = None,
    ) -> None:
        window_size = max(1, int(round(sample_rate * window_seconds)))
        hop_size = max(1, int(round(window_size * (1 - overlap))))
        self._sample_rate = sample_rate
        self._buffer = SlidingWindowBuffer(window_size=window_size, hop_size=hop_size)
        self._band_type = band_type
        self._n_mfcc = n_mfcc
        self._fft_size = fft_size
        self._hop_length = hop_length
        self._baseline = baseline
        self._window_index = 0

    def set_baseline(self, baseline: AcousticBaseline | None) -> None:
        self._baseline = baseline

    def process_chunk(self, chunk: SampleChunk, source_description: str) -> list[AcousticEvidence]:
        windows = self._buffer.push(chunk.samples)
        evidence: list[AcousticEvidence] = []
        for window in windows:
            features = extract_acoustic_features(
                window,
                sample_rate=self._sample_rate,
                band_type=self._band_type,
                n_mfcc=self._n_mfcc,
                fft_size=self._fft_size,
                hop_length=self._hop_length,
            )

            deviation: dict[str, float] = {}
            if self._baseline is not None:
                for name, (mean, std) in self._baseline.feature_stats.items():
                    value = getattr(features, name, None)
                    if not isinstance(value, (int, float)) or std <= 0:
                        continue
                    deviation[name] = (value - mean) / std

            evidence.append(
                AcousticEvidence(
                    window_index=self._window_index,
                    timestamp=chunk.timestamp,
                    source_description=source_description,
                    features=features,
                    baseline_deviation=deviation,
                )
            )
            self._window_index += 1
        return evidence
