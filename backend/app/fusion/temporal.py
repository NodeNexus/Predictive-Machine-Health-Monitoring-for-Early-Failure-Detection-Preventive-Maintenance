"""Temporal smoothing and hysteresis-based event confirmation.

A single abnormal cycle should not immediately raise a critical event, and
a single normal cycle after a sustained fault should not immediately clear
it - both thresholds are configurable (see app.core.config.settings).
"""
from __future__ import annotations

from pydantic import BaseModel

from app.models.schemas import HealthStatus


class TemporalUpdate(BaseModel):
    smoothed_health_score: float | None
    event_active: bool
    event_just_started: bool
    event_just_cleared: bool
    abnormal_streak: int
    normal_streak: int


class TemporalHealthTracker:
    def __init__(self, alpha: float, persistence_frames: int, clear_frames: int) -> None:
        self._alpha = alpha
        self._persistence_frames = persistence_frames
        self._clear_frames = clear_frames
        self._smoothed_score: float | None = None
        self._abnormal_streak = 0
        self._normal_streak = 0
        self._event_active = False

    def update(self, health_score: float | None, status: HealthStatus) -> TemporalUpdate:
        if health_score is not None:
            self._smoothed_score = (
                health_score
                if self._smoothed_score is None
                else self._alpha * health_score + (1 - self._alpha) * self._smoothed_score
            )

        is_abnormal = status in ("warning", "critical")
        if is_abnormal:
            self._abnormal_streak += 1
            self._normal_streak = 0
        else:
            self._normal_streak += 1
            self._abnormal_streak = 0

        event_just_started = False
        event_just_cleared = False

        if not self._event_active and self._abnormal_streak >= self._persistence_frames:
            self._event_active = True
            event_just_started = True
        elif self._event_active and self._normal_streak >= self._clear_frames:
            self._event_active = False
            event_just_cleared = True

        return TemporalUpdate(
            smoothed_health_score=round(self._smoothed_score, 1) if self._smoothed_score is not None else None,
            event_active=self._event_active,
            event_just_started=event_just_started,
            event_just_cleared=event_just_cleared,
            abnormal_streak=self._abnormal_streak,
            normal_streak=self._normal_streak,
        )
