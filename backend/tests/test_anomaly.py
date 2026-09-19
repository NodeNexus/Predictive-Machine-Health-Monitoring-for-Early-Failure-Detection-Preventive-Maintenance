import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.anomaly.baseline import BaselineEstimator
from app.anomaly.detector import LayeredAnomalyDetector
from app.anomaly.isolation_forest import IsolationForestDetector
from app.anomaly.repository import load_baseline, save_baseline
from app.anomaly.statistical import classify_from_zscores, compute_statistical_deviation
from app.database.session import SessionLocal
from app.main import app


def test_baseline_estimator_computes_correct_stats():
    est = BaselineEstimator(modality="vibration")
    rng = np.random.default_rng(0)
    for _ in range(200):
        est.add_observation({"rms": float(rng.normal(0.5, 0.05)), "kurtosis": float(rng.normal(3.0, 0.2))})

    assert est.is_ready(min_observations=100)
    stats = est.compute_stats()
    assert stats.observation_count == 200
    assert stats.feature_stats["rms"].mean == pytest.approx(0.5, abs=0.02)
    assert stats.feature_stats["rms"].std == pytest.approx(0.05, abs=0.02)


def test_baseline_estimator_not_ready_below_threshold():
    est = BaselineEstimator(modality="acoustic")
    for _ in range(5):
        est.add_observation({"rms": 0.1})
    assert not est.is_ready(min_observations=30)


def test_baseline_feature_matrix_alignment():
    est = BaselineEstimator(modality="vibration")
    est.add_observation({"a": 1.0, "b": 2.0})
    est.add_observation({"a": 3.0})  # missing "b" - should be excluded from the matrix
    est.add_observation({"a": 5.0, "b": 6.0})

    matrix = est.feature_matrix(["a", "b"])
    assert matrix is not None
    assert matrix.shape == (2, 2)
    assert list(matrix[:, 0]) == [1.0, 5.0]


def test_statistical_deviation_and_classification():
    from app.anomaly.baseline import BaselineStats, FeatureStat

    baseline = BaselineStats(
        modality="vibration",
        observation_count=100,
        feature_stats={"rms": FeatureStat(mean=0.5, std=0.1, p5=0.3, p95=0.7, min=0.2, max=0.9)},
    )
    zscores = compute_statistical_deviation({"rms": 0.9}, baseline)
    assert zscores["rms"] == pytest.approx(4.0)

    status, contributing = classify_from_zscores(zscores, threshold=3.0)
    assert status == "anomalous"
    assert contributing == ["rms"]

    status2, contributing2 = classify_from_zscores({"rms": 1.0}, threshold=3.0)
    assert status2 == "normal"
    assert contributing2 == []


def test_isolation_forest_flags_outlier():
    rng = np.random.default_rng(1)
    normal_data = rng.normal(loc=[0.5, 3.0], scale=[0.05, 0.2], size=(200, 2))

    detector = IsolationForestDetector(feature_names=["rms", "kurtosis"], contamination=0.05)
    assert not detector.is_fitted
    detector.fit(normal_data)
    assert detector.is_fitted

    inlier_result = detector.score({"rms": 0.5, "kurtosis": 3.0})
    outlier_result = detector.score({"rms": 5.0, "kurtosis": 30.0})

    assert inlier_result is not None and inlier_result[0] == "normal"
    assert outlier_result is not None and outlier_result[0] == "anomalous"


def test_isolation_forest_returns_none_for_missing_features():
    detector = IsolationForestDetector(feature_names=["rms", "kurtosis"])
    detector.fit(np.random.default_rng(2).normal(size=(50, 2)))
    assert detector.score({"rms": 0.5}) is None  # kurtosis missing


def test_layered_detector_reports_unknown_without_baseline():
    detector = LayeredAnomalyDetector(modality="vibration", z_threshold=3.0, min_baseline_observations=30)
    result = detector.evaluate({"rms": 0.5}, baseline=None)
    assert result.status == "unknown"
    assert result.reason is not None


def test_layered_detector_normal_and_anomalous_via_statistics():
    from app.anomaly.baseline import BaselineStats, FeatureStat

    baseline = BaselineStats(
        modality="vibration",
        observation_count=100,
        feature_stats={"rms": FeatureStat(mean=0.5, std=0.05, p5=0.4, p95=0.6, min=0.3, max=0.7)},
    )
    detector = LayeredAnomalyDetector(modality="vibration", z_threshold=3.0, min_baseline_observations=30)

    normal_result = detector.evaluate({"rms": 0.51}, baseline)
    assert normal_result.status == "normal"

    anomalous_result = detector.evaluate({"rms": 1.0}, baseline)
    assert anomalous_result.status == "anomalous"
    assert "rms" in anomalous_result.statistical_contributing_features


def test_layered_detector_isolation_forest_can_flag_even_when_statistics_dont():
    from app.anomaly.baseline import BaselineStats, FeatureStat

    # Baseline z-score alone won't flag this (within 3 std), but isolation
    # forest trained on a tight joint distribution should catch the
    # combination as unusual.
    baseline = BaselineStats(
        modality="vibration",
        observation_count=100,
        feature_stats={
            "rms": FeatureStat(mean=0.5, std=0.2, p5=0.3, p95=0.7, min=0.1, max=0.9),
            "kurtosis": FeatureStat(mean=3.0, std=0.5, p5=2.5, p95=3.5, min=2.0, max=4.0),
        },
    )
    rng = np.random.default_rng(3)
    normal_data = rng.normal(loc=[0.5, 3.0], scale=[0.03, 0.05], size=(200, 2))
    forest = IsolationForestDetector(feature_names=["rms", "kurtosis"], contamination=0.05)
    forest.fit(normal_data)

    detector = LayeredAnomalyDetector(modality="vibration", z_threshold=3.0, min_baseline_observations=30)
    detector.set_isolation_forest(forest)

    features = {"rms": 1.0, "kurtosis": 3.0}  # within 3 std of rms per the loose baseline, but far in joint space
    result = detector.evaluate(features, baseline)
    assert result.isolation_forest_status == "anomalous"
    assert result.status == "anomalous"  # combined status picks it up even though statistics alone might not


def test_baseline_repository_roundtrip():
    with TestClient(app):  # triggers init_db via lifespan
        db = SessionLocal()
        try:
            create_resp_machine_id = "test-machine-baseline-roundtrip"
            from app.database.models import Machine

            if db.get(Machine, create_resp_machine_id) is None:
                db.add(Machine(machine_id=create_resp_machine_id, machine_name="Roundtrip Test"))
                db.commit()

            est = BaselineEstimator(modality="thermal")
            for _ in range(40):
                est.add_observation({"mean_intensity": 100.0})
            stats = est.compute_stats()

            save_baseline(db, create_resp_machine_id, stats)
            loaded = load_baseline(db, create_resp_machine_id, "thermal")

            assert loaded is not None
            assert loaded.observation_count == 40
            assert loaded.feature_stats["mean_intensity"].mean == pytest.approx(100.0)

            machine = db.get(Machine, create_resp_machine_id)
            assert machine.baseline_status == "calibrated"
        finally:
            db.close()
