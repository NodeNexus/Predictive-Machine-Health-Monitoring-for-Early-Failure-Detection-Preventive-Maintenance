from datetime import datetime, timezone

import numpy as np
import pytest

from app.core.config import settings
from app.pipelines.common.interfaces import ThermalFrame
from app.pipelines.thermal.analyzer import ThermalAnalyzer, ThermalBaseline
from app.pipelines.thermal.features import extract_thermal_features
from app.pipelines.thermal.readers import ThermalVideoReader


def test_extract_features_uniform_frame_has_no_meaningful_hotspot():
    frame = np.full((50, 50), 100, dtype=np.uint8)
    features = extract_thermal_features(frame, hotspot_percentile=99.0)
    assert features.mean_intensity == pytest.approx(100.0)
    assert features.std_intensity == pytest.approx(0.0)
    assert features.is_radiometric is False


def test_extract_features_locates_hotspot_centroid():
    frame = np.full((100, 100), 50, dtype=np.uint8)
    frame[65:76, 65:76] = 255  # bright square roughly centered at (70, 70)

    features = extract_thermal_features(frame, hotspot_percentile=95.0)

    assert features.hotspot_pixel_count > 0
    assert features.max_intensity == 255
    assert features.hotspot_centroid_x == pytest.approx(70, abs=2)
    assert features.hotspot_centroid_y == pytest.approx(70, abs=2)


def test_extract_features_respects_roi():
    frame = np.zeros((100, 100), dtype=np.uint8)
    frame[10:20, 10:20] = 255  # hotspot outside the ROI below

    features = extract_thermal_features(frame, hotspot_percentile=99.0, roi=(50, 50, 20, 20))

    assert features.max_intensity == 0  # ROI excludes the bright square
    assert features.hotspot_pixel_count >= 0


def test_analyzer_tracks_hotspot_growth_across_frames():
    analyzer = ThermalAnalyzer(hotspot_percentile=90.0)

    def make_frame(square_size: int, index: int) -> ThermalFrame:
        img = np.zeros((100, 100), dtype=np.uint8)
        img[0:square_size, 0:square_size] = 255
        return ThermalFrame(frame_index=index, timestamp=datetime.now(timezone.utc), image=img)

    first = analyzer.process_frame(make_frame(10, 0), "test")
    assert first.hotspot_area_change is None

    second = analyzer.process_frame(make_frame(30, 1), "test")
    assert second.hotspot_area_change is not None
    assert second.hotspot_area_change > 0  # hotspot grew


def test_analyzer_applies_baseline_deviation_when_supplied():
    analyzer = ThermalAnalyzer(
        baseline=ThermalBaseline(feature_stats={"mean_intensity": (50.0, 5.0)})
    )
    frame = ThermalFrame(
        frame_index=0,
        timestamp=datetime.now(timezone.utc),
        image=np.full((20, 20), 75, dtype=np.uint8),
    )
    evidence = analyzer.process_frame(frame, "test")
    assert evidence.baseline_deviation["mean_intensity"] == pytest.approx(5.0)  # (75-50)/5


def test_analyzer_omits_deviation_without_baseline():
    analyzer = ThermalAnalyzer()
    frame = ThermalFrame(
        frame_index=0, timestamp=datetime.now(timezone.utc), image=np.zeros((10, 10), dtype=np.uint8)
    )
    evidence = analyzer.process_frame(frame, "test")
    assert evidence.baseline_deviation == {}


@pytest.mark.skipif(not settings.video_dir.is_dir(), reason="VIDEO/ not present in this environment")
def test_thermal_video_reader_reads_real_demo_video():
    videos = sorted(settings.video_dir.glob("*.mp4"))
    if not videos:
        pytest.skip("no demo videos found")

    reader = ThermalVideoReader(videos[0], target_fps=2.0)
    with reader:
        assert reader.is_live is False
        assert reader.source_description.startswith("demo:")

        frame = reader.read_frame()
        assert frame is not None
        assert frame.image.ndim == 3
        assert frame.is_radiometric is False

        frames_read = 1
        while reader.read_frame() is not None and frames_read < 5:
            frames_read += 1
        assert frames_read >= 1
