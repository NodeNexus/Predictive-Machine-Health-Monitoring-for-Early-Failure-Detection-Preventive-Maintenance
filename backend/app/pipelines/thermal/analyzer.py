"""Stateful thermal analysis: feature extraction + temporal hotspot tracking.

Baseline comparison is optional and only produces a deviation when a
baseline is actually supplied (Phase 6 wires this to the persisted
per-machine baseline). Without one, evidence honestly omits `deviation`
rather than comparing against an invented threshold.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.pipelines.common.interfaces import ThermalFrame
from app.pipelines.thermal.features import ThermalFeatures, extract_thermal_features


class ThermalBaseline(BaseModel):
    """Per-feature mean/std, as produced by the baseline engine (Phase 6)."""

    feature_stats: dict[str, tuple[float, float]]  # feature_name -> (mean, std)


class ThermalEvidence(BaseModel):
    frame_index: int
    timestamp: datetime
    source_description: str
    features: ThermalFeatures
    hotspot_area_change: float | None = None  # vs previous frame; None on first frame
    baseline_deviation: dict[str, float] = {}  # feature -> z-score, only if baseline supplied


class ThermalAnalyzer:
    def __init__(
        self,
        hotspot_percentile: float = 99.0,
        roi: tuple[int, int, int, int] | None = None,
        baseline: ThermalBaseline | None = None,
    ) -> None:
        self._hotspot_percentile = hotspot_percentile
        self._roi = roi
        self._baseline = baseline
        self._previous_hotspot_area: float | None = None

    def set_baseline(self, baseline: ThermalBaseline | None) -> None:
        self._baseline = baseline

    def process_frame(self, frame: ThermalFrame, source_description: str) -> ThermalEvidence:
        features = extract_thermal_features(
            frame.image,
            hotspot_percentile=self._hotspot_percentile,
            is_radiometric=frame.is_radiometric,
            roi=self._roi,
        )

        hotspot_area_change: float | None = None
        if self._previous_hotspot_area is not None:
            hotspot_area_change = features.hotspot_area_fraction - self._previous_hotspot_area
        self._previous_hotspot_area = features.hotspot_area_fraction

        deviation: dict[str, float] = {}
        if self._baseline is not None:
            for name, (mean, std) in self._baseline.feature_stats.items():
                value = getattr(features, name, None)
                if value is None or std <= 0:
                    continue
                deviation[name] = (value - mean) / std

        return ThermalEvidence(
            frame_index=frame.frame_index,
            timestamp=frame.timestamp,
            source_description=source_description,
            features=features,
            hotspot_area_change=hotspot_area_change,
            baseline_deviation=deviation,
        )
