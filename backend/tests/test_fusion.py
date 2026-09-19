from datetime import datetime, timezone

import pytest

from app.anomaly.detector import AnomalyResult
from app.fusion.engine import FusionEngine, ModalitySnapshot
from app.fusion.temporal import TemporalHealthTracker

NOW = datetime.now(timezone.utc)


def _snapshot(modality, status, zscores=None, contributing=None, if_status=None, if_score=None, reason=None, raw=None):
    return ModalitySnapshot(
        modality=modality,
        anomaly=AnomalyResult(
            modality=modality,
            status=status,
            reason=reason,
            statistical_zscores=zscores or {},
            statistical_contributing_features=contributing or [],
            isolation_forest_status=if_status,
            isolation_forest_score=if_score,
        ),
        raw_features=raw or {},
    )


def test_fusion_all_unknown_returns_unknown_state():
    engine = FusionEngine()
    snapshots = [_snapshot("thermal", "unknown", reason="No baseline yet")]
    state = engine.combine("m1", NOW, snapshots)

    assert state.status == "unknown"
    assert state.confidence == 0.0
    assert set(state.missing_modalities) == {"vibration", "acoustic"}
    assert state.evidence[0].note == "No baseline yet"


def test_fusion_single_modality_available_reports_missing_others():
    engine = FusionEngine()
    snapshots = [_snapshot("thermal", "normal")]
    state = engine.combine("m1", NOW, snapshots)

    assert state.status == "normal"
    assert state.health_score == 100.0
    assert set(state.missing_modalities) == {"vibration", "acoustic"}
    assert state.confidence == pytest.approx(1 / 3, abs=0.01)


def test_fusion_all_normal_gives_full_confidence_and_score():
    engine = FusionEngine()
    snapshots = [
        _snapshot("thermal", "normal"),
        _snapshot("vibration", "normal"),
        _snapshot("acoustic", "normal"),
    ]
    state = engine.combine("m1", NOW, snapshots)

    assert state.status == "normal"
    assert state.health_score == 100.0
    assert state.confidence == 1.0
    assert state.missing_modalities == []


def test_fusion_single_anomalous_modality_is_warning_not_critical():
    engine = FusionEngine()
    snapshots = [
        _snapshot("thermal", "normal"),
        _snapshot(
            "vibration",
            "anomalous",
            zscores={"rms": 4.0},
            contributing=["rms"],
            raw={"rms": 0.9},
        ),
        _snapshot("acoustic", "normal"),
    ]
    state = engine.combine("m1", NOW, snapshots)

    assert state.status == "warning"
    assert state.health_score < 100.0
    assert any(e.modality == "vibration" and e.feature == "rms" for e in state.evidence)


def test_fusion_two_anomalous_modalities_escalates_to_critical():
    engine = FusionEngine()
    snapshots = [
        _snapshot("thermal", "anomalous", zscores={"mean_intensity": 5.0}, contributing=["mean_intensity"]),
        _snapshot("vibration", "anomalous", zscores={"rms": 5.0}, contributing=["rms"]),
        _snapshot("acoustic", "normal"),
    ]
    state = engine.combine("m1", NOW, snapshots)
    assert state.status == "critical"


def test_fusion_high_severity_single_modality_escalates_to_critical():
    engine = FusionEngine(critical_z_threshold=6.0, severity_z_cap=10.0)
    snapshots = [_snapshot("vibration", "anomalous", zscores={"rms": 9.0}, contributing=["rms"])]
    state = engine.combine("m1", NOW, snapshots)
    assert state.status == "critical"


def test_fusion_isolation_forest_only_flag_still_produces_evidence():
    engine = FusionEngine()
    snapshots = [
        _snapshot(
            "acoustic",
            "anomalous",
            zscores={},
            contributing=[],
            if_status="anomalous",
            if_score=-0.15,
        )
    ]
    state = engine.combine("m1", NOW, snapshots)
    assert state.status in ("warning", "critical")
    assert any(e.feature == "isolation_forest" for e in state.evidence)


def test_temporal_tracker_smooths_score():
    tracker = TemporalHealthTracker(alpha=0.5, persistence_frames=3, clear_frames=3)
    first = tracker.update(100.0, "normal")
    second = tracker.update(50.0, "warning")
    assert first.smoothed_health_score == 100.0
    assert second.smoothed_health_score == pytest.approx(75.0)


def test_temporal_tracker_requires_persistence_before_raising_event():
    tracker = TemporalHealthTracker(alpha=0.3, persistence_frames=3, clear_frames=3)
    u1 = tracker.update(60.0, "warning")
    u2 = tracker.update(60.0, "warning")
    assert not u1.event_active
    assert not u2.event_active
    u3 = tracker.update(60.0, "warning")
    assert u3.event_active
    assert u3.event_just_started


def test_temporal_tracker_requires_hysteresis_before_clearing_event():
    tracker = TemporalHealthTracker(alpha=0.3, persistence_frames=2, clear_frames=3)
    tracker.update(50.0, "warning")
    started = tracker.update(50.0, "warning")
    assert started.event_active

    u1 = tracker.update(95.0, "normal")
    u2 = tracker.update(95.0, "normal")
    assert u1.event_active and not u1.event_just_cleared
    assert u2.event_active and not u2.event_just_cleared

    u3 = tracker.update(95.0, "normal")
    assert not u3.event_active
    assert u3.event_just_cleared


def test_temporal_tracker_single_blip_does_not_raise_event():
    tracker = TemporalHealthTracker(alpha=0.3, persistence_frames=5, clear_frames=5)
    tracker.update(50.0, "critical")  # one bad frame
    result = tracker.update(95.0, "normal")  # immediately recovers
    assert not result.event_active
