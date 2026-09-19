"""Level 1: statistical baseline-deviation anomaly detection."""
from __future__ import annotations

from typing import Literal

from app.anomaly.baseline import BaselineStats


def compute_statistical_deviation(features: dict[str, float], baseline: BaselineStats) -> dict[str, float]:
    zscores: dict[str, float] = {}
    for name, value in features.items():
        if not isinstance(value, (int, float)):
            continue
        stat = baseline.feature_stats.get(name)
        if stat is None or stat.std <= 0:
            continue
        zscores[name] = (value - stat.mean) / stat.std
    return zscores


def classify_from_zscores(
    zscores: dict[str, float], threshold: float
) -> tuple[Literal["normal", "anomalous"], list[str]]:
    contributing = sorted(
        (name for name, z in zscores.items() if abs(z) >= threshold),
        key=lambda name: -abs(zscores[name]),
    )
    status: Literal["normal", "anomalous"] = "anomalous" if contributing else "normal"
    return status, contributing
