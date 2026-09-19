"""Level 2: classical ML anomaly detection (Isolation Forest).

Trained on a machine's own accumulated baseline observations (assumed
normal-operation data, per the baseline-calibration workflow) - never
force-fit with too little data.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from sklearn.ensemble import IsolationForest


class IsolationForestDetector:
    def __init__(self, feature_names: list[str], contamination: float | str = "auto", random_state: int = 42) -> None:
        self._feature_names = feature_names
        self._model = IsolationForest(contamination=contamination, random_state=random_state)
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    def fit(self, X: np.ndarray) -> None:
        self._model.fit(X)
        self._fitted = True

    def score(self, features: dict[str, float]) -> tuple[Literal["normal", "anomalous"], float] | None:
        if not self._fitted:
            return None
        row = [features.get(name) for name in self._feature_names]
        if any(v is None for v in row):
            return None  # required features missing this frame - can't score, not "normal by default"

        x = np.array(row, dtype=np.float64).reshape(1, -1)
        prediction = int(self._model.predict(x)[0])  # 1 = normal (inlier), -1 = anomaly (outlier)
        score = float(self._model.decision_function(x)[0])  # higher = more normal
        status: Literal["normal", "anomalous"] = "normal" if prediction == 1 else "anomalous"
        return status, score
