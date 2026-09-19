"""Layered anomaly detection: statistical baseline -> classical ML.

Level 3 (deep learning / learned feature models) is intentionally not
implemented - there isn't yet a validated dataset/training setup that
would justify it (see docs/DEVELOPMENT.md). The layering is designed so
adding it later means adding a third opinion here, not restructuring
this module.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.anomaly.baseline import BaselineStats
from app.anomaly.isolation_forest import IsolationForestDetector
from app.anomaly.statistical import classify_from_zscores, compute_statistical_deviation

AnomalyStatus = Literal["normal", "anomalous", "unknown"]


class AnomalyResult(BaseModel):
    modality: str
    status: AnomalyStatus
    reason: str | None = None
    statistical_zscores: dict[str, float] = {}
    statistical_contributing_features: list[str] = []
    isolation_forest_status: Literal["normal", "anomalous"] | None = None
    isolation_forest_score: float | None = None


class LayeredAnomalyDetector:
    def __init__(self, modality: str, z_threshold: float, min_baseline_observations: int) -> None:
        self._modality = modality
        self._z_threshold = z_threshold
        self._min_observations = min_baseline_observations
        self._isolation_forest: IsolationForestDetector | None = None

    def set_isolation_forest(self, detector: IsolationForestDetector | None) -> None:
        self._isolation_forest = detector

    def evaluate(self, features: dict[str, float], baseline: BaselineStats | None) -> AnomalyResult:
        if baseline is None or baseline.observation_count < self._min_observations:
            return AnomalyResult(
                modality=self._modality,
                status="unknown",
                reason=(
                    "No baseline yet"
                    if baseline is None
                    else f"Baseline has only {baseline.observation_count} observation(s), "
                    f"needs {self._min_observations}"
                ),
            )

        zscores = compute_statistical_deviation(features, baseline)
        statistical_status, contributing = classify_from_zscores(zscores, self._z_threshold)

        isolation_status: Literal["normal", "anomalous"] | None = None
        isolation_score: float | None = None
        if self._isolation_forest is not None and self._isolation_forest.is_fitted:
            result = self._isolation_forest.score(features)
            if result is not None:
                isolation_status, isolation_score = result

        # Conservative combination: either layer flagging it is enough to
        # raise anomalous (favors recall - a missed real fault is worse
        # than an extra "requires inspection" evidence entry downstream).
        final_status: AnomalyStatus = (
            "anomalous" if statistical_status == "anomalous" or isolation_status == "anomalous" else "normal"
        )

        return AnomalyResult(
            modality=self._modality,
            status=final_status,
            statistical_zscores=zscores,
            statistical_contributing_features=contributing,
            isolation_forest_status=isolation_status,
            isolation_forest_score=isolation_score,
        )
