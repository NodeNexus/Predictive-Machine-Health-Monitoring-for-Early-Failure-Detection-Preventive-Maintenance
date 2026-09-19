"""Per-machine, per-modality baseline estimation.

Observations are kept as a bounded deque of full feature-dicts (not
per-feature lists) so rows stay index-aligned for building a training
matrix, and memory is bounded regardless of how long monitoring runs.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from pydantic import BaseModel


class FeatureStat(BaseModel):
    mean: float
    std: float
    p5: float
    p95: float
    min: float
    max: float


class BaselineStats(BaseModel):
    modality: str
    feature_stats: dict[str, FeatureStat]
    observation_count: int


class BaselineEstimator:
    def __init__(self, modality: str, max_buffer: int = 5000) -> None:
        self._modality = modality
        self._buffer: deque[dict[str, float]] = deque(maxlen=max_buffer)
        self._count = 0

    @property
    def observation_count(self) -> int:
        return self._count

    def is_ready(self, min_observations: int) -> bool:
        return self._count >= min_observations

    def add_observation(self, features: dict[str, float]) -> None:
        numeric = {k: float(v) for k, v in features.items() if isinstance(v, (int, float))}
        if numeric:
            self._buffer.append(numeric)
        self._count += 1

    def compute_stats(self) -> BaselineStats:
        keys: set[str] = set()
        for entry in self._buffer:
            keys.update(entry.keys())

        feature_stats: dict[str, FeatureStat] = {}
        for key in keys:
            values = np.array([entry[key] for entry in self._buffer if key in entry], dtype=np.float64)
            if len(values) < 2:
                continue
            feature_stats[key] = FeatureStat(
                mean=float(np.mean(values)),
                std=float(np.std(values)),
                p5=float(np.percentile(values, 5)),
                p95=float(np.percentile(values, 95)),
                min=float(np.min(values)),
                max=float(np.max(values)),
            )

        return BaselineStats(modality=self._modality, feature_stats=feature_stats, observation_count=self._count)

    def feature_matrix(self, feature_names: list[str]) -> np.ndarray | None:
        """Rows containing all of `feature_names`, for model training. None if fewer than 2 rows qualify."""
        rows = [
            [entry[name] for name in feature_names]
            for entry in self._buffer
            if all(name in entry for name in feature_names)
        ]
        if len(rows) < 2:
            return None
        return np.array(rows, dtype=np.float64)
