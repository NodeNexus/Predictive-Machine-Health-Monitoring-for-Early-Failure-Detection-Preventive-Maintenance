"""Stateful, windowed vibration analysis."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.pipelines.common.interfaces import SampleChunk, SlidingWindowBuffer
from app.pipelines.common.octave import BandType
from app.pipelines.vibration.features import (
    BearingGeometry,
    VibrationFeatures,
    extract_vibration_features,
)


class VibrationBaseline(BaseModel):
    feature_stats: dict[str, tuple[float, float]]  # feature_name -> (mean, std)


class VibrationEvidence(BaseModel):
    window_index: int
    timestamp: datetime
    source_description: str
    features: VibrationFeatures
    baseline_deviation: dict[str, float] = {}


class VibrationAnalyzer:
    def __init__(
        self,
        sample_rate: float,
        window_seconds: float = 1.0,
        overlap: float = 0.5,
        rpm: float | None = None,
        bearing_geometry: BearingGeometry | None = None,
        band_type: BandType = "octave",
        baseline: VibrationBaseline | None = None,
    ) -> None:
        window_size = max(1, int(round(sample_rate * window_seconds)))
        hop_size = max(1, int(round(window_size * (1 - overlap))))
        self._sample_rate = sample_rate
        self._buffer = SlidingWindowBuffer(window_size=window_size, hop_size=hop_size)
        self._rpm = rpm
        self._bearing_geometry = bearing_geometry
        self._band_type = band_type
        self._baseline = baseline
        self._window_index = 0

    def set_baseline(self, baseline: VibrationBaseline | None) -> None:
        self._baseline = baseline

    def process_chunk(self, chunk: SampleChunk, source_description: str) -> list[VibrationEvidence]:
        windows = self._buffer.push(chunk.samples)
        evidence: list[VibrationEvidence] = []
        for window in windows:
            features = extract_vibration_features(
                window,
                sample_rate=self._sample_rate,
                rpm=self._rpm,
                bearing_geometry=self._bearing_geometry,
                band_type=self._band_type,
            )

            deviation: dict[str, float] = {}
            if self._baseline is not None:
                for name, (mean, std) in self._baseline.feature_stats.items():
                    value = getattr(features, name, None)
                    if value is None or std <= 0:
                        continue
                    deviation[name] = (value - mean) / std

            evidence.append(
                VibrationEvidence(
                    window_index=self._window_index,
                    timestamp=chunk.timestamp,
                    source_description=source_description,
                    features=features,
                    baseline_deviation=deviation,
                )
            )
            self._window_index += 1
        return evidence
