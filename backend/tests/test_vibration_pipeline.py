import numpy as np
import pytest

from app.core.config import settings
from app.pipelines.vibration.analyzer import VibrationAnalyzer, VibrationBaseline
from app.pipelines.common.interfaces import SampleChunk
from app.pipelines.vibration.features import (
    BearingGeometry,
    compute_bearing_fault_frequencies,
    extract_vibration_features,
)
from app.pipelines.vibration.readers import IMSVibrationDatasetReader, LiveVibrationSensor
from datetime import datetime, timezone


def _sine(freq: float, sample_rate: float, n: int, amplitude: float = 1.0) -> np.ndarray:
    t = np.arange(n) / sample_rate
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_extract_features_identifies_dominant_frequency():
    sr = 20000.0
    window = _sine(500.0, sr, n=20480, amplitude=2.0)
    features = extract_vibration_features(window, sample_rate=sr)

    assert features.dominant_frequency == pytest.approx(500.0, abs=5.0)
    assert features.peak == pytest.approx(2.0, abs=0.05)
    assert features.crest_factor > 1.0
    assert features.analysis_type == "generic_spectral"
    assert features.bearing_fault_frequencies is None


def test_extract_features_without_geometry_stays_generic():
    window = _sine(200.0, 20000.0, n=4096)
    features = extract_vibration_features(window, sample_rate=20000.0, rpm=2000)
    # RPM alone (no geometry) must NOT trigger bearing-specific analysis
    assert features.analysis_type == "generic_spectral"
    assert features.bearing_fault_frequencies is None


def test_extract_features_with_rpm_and_geometry_computes_bearing_frequencies():
    geometry = BearingGeometry(n_balls=9, ball_diameter_mm=7.94, pitch_diameter_mm=39.0, contact_angle_deg=0.0)
    window = _sine(200.0, 20000.0, n=4096)
    features = extract_vibration_features(window, sample_rate=20000.0, rpm=1800, bearing_geometry=geometry)

    assert features.analysis_type == "bearing_specific"
    assert features.bearing_fault_frequencies is not None
    freqs = features.bearing_fault_frequencies
    assert freqs.bpfo > 0 and freqs.bpfi > 0 and freqs.bsf > 0 and freqs.ftf > 0
    assert freqs.bpfi > freqs.bpfo  # true for this geometry (inner race always faster for zero contact angle)


def test_compute_bearing_fault_frequencies_known_values():
    # Textbook check: for a bearing with many balls at 0 contact angle,
    # BPFO + BPFI should approximately equal n * fr (ball pass frequencies split the shaft rate by ball count)
    geometry = BearingGeometry(n_balls=8, ball_diameter_mm=10.0, pitch_diameter_mm=50.0)
    freqs = compute_bearing_fault_frequencies(rpm=3000, geometry=geometry)
    fr = 3000 / 60.0
    assert freqs.bpfo + freqs.bpfi == pytest.approx(8 * fr, rel=0.01)


def test_analyzer_produces_windows_from_streamed_chunks():
    sr = 1000.0
    analyzer = VibrationAnalyzer(sample_rate=sr, window_seconds=1.0, overlap=0.0)
    signal = _sine(50.0, sr, n=3500)

    chunk = SampleChunk(samples=signal, sample_rate=sr, timestamp=datetime.now(timezone.utc))
    evidence = analyzer.process_chunk(chunk, "test")

    assert len(evidence) == 3  # 3500 samples / 1000-sample windows = 3 complete windows
    assert evidence[0].features.dominant_frequency == pytest.approx(50.0, abs=2.0)
    assert evidence[0].window_index == 0
    assert evidence[1].window_index == 1


def test_analyzer_baseline_deviation():
    analyzer = VibrationAnalyzer(
        sample_rate=1000.0,
        window_seconds=1.0,
        overlap=0.0,
        baseline=VibrationBaseline(feature_stats={"rms": (0.5, 0.1)}),
    )
    signal = _sine(50.0, 1000.0, n=1000, amplitude=1.0)
    chunk = SampleChunk(samples=signal, sample_rate=1000.0, timestamp=datetime.now(timezone.utc))
    evidence = analyzer.process_chunk(chunk, "test")

    assert len(evidence) == 1
    assert "rms" in evidence[0].baseline_deviation


@pytest.mark.skipif(
    not (settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test").is_dir(),
    reason="IMS dataset not extracted in this environment",
)
def test_ims_reader_streams_real_data():
    test_dir = settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test"
    reader = IMSVibrationDatasetReader(test_dir, channel=0, sample_rate=20000.0)
    with reader:
        assert reader.is_live is False
        chunk = reader.read_chunk(5000)
        assert chunk is not None
        assert len(chunk.samples) == 5000
        assert chunk.sample_rate == 20000.0


@pytest.mark.skipif(
    not (settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test").is_dir(),
    reason="IMS dataset not extracted in this environment",
)
def test_ims_reader_bounded_range_limits_file_count():
    test_dir = settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test"

    reader = IMSVibrationDatasetReader(test_dir, channel=4, sample_rate=20000.0, start_file=0, end_file=1)
    with reader:
        assert "[0:1]" in reader.source_description
        # exactly 2 files' worth of samples (20480 each) should be available, no more
        total = 0
        while True:
            chunk = reader.read_chunk(50000)
            if chunk is None:
                break
            total += len(chunk.samples)
        assert total == 2 * 20480


def test_ims_reader_default_range_unchanged():
    # Backward compatibility: omitting start_file/end_file must not add a
    # range suffix or otherwise change existing behavior.
    reader = IMSVibrationDatasetReader("dummy_path", channel=0, sample_rate=20000.0)
    assert reader.source_description == "demo:dummy_path#channel0"


@pytest.mark.skipif(
    not (settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test").is_dir(),
    reason="IMS dataset not extracted in this environment",
)
def test_ims_reader_rejects_invalid_range():
    test_dir = settings.dataset_dir / "IMS" / "IMS" / "1st_test" / "1st_test"
    reader = IMSVibrationDatasetReader(test_dir, channel=4, sample_rate=20000.0, start_file=5, end_file=999999)
    with pytest.raises(ValueError):
        reader.open()

        chunk2 = reader.read_chunk(20480)
        assert chunk2 is not None


def test_live_vibration_sensor_reports_not_connected():
    sensor = LiveVibrationSensor(device_id="daq-0")
    assert sensor.is_live is True
    with pytest.raises(ConnectionError):
        sensor.open()
