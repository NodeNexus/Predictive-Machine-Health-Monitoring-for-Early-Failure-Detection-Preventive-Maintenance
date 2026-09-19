from datetime import datetime, timezone

import numpy as np
import pytest

from app.core.config import settings
from app.pipelines.acoustic.analyzer import AcousticAnalyzer, AcousticBaseline
from app.pipelines.acoustic.features import extract_acoustic_features
from app.pipelines.acoustic.readers import AudioFileReader, LiveMicrophone
from app.pipelines.common.interfaces import SampleChunk


def _sine(freq: float, sample_rate: float, n: int, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(n) / sample_rate
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_extract_features_identifies_dominant_frequency_and_mfcc_shape():
    sr = 16000.0
    window = _sine(1000.0, sr, n=16000)
    features = extract_acoustic_features(window, sample_rate=sr, n_mfcc=13)

    assert features.dominant_frequency == pytest.approx(1000.0, abs=10.0)
    assert len(features.mfcc) == 13
    assert features.rms > 0
    assert features.crest_factor > 1.0
    # a pure tone should have a band structure concentrated near 1kHz
    band_1000 = next(b for b in features.band_energies.bands if round(b.center_frequency) == 1000)
    other_energy = sum(b.energy for b in features.band_energies.bands if round(b.center_frequency) != 1000)
    assert band_1000.energy > other_energy


def test_extract_features_flatness_distinguishes_noise_from_tone():
    sr = 16000.0
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.1, size=16000)
    tone = _sine(1000.0, sr, n=16000)

    noise_features = extract_acoustic_features(noise, sample_rate=sr)
    tone_features = extract_acoustic_features(tone, sample_rate=sr)

    # white noise has a flatter spectrum (flatness closer to 1) than a pure tone
    assert noise_features.spectral_flatness > tone_features.spectral_flatness


def test_analyzer_produces_windows_and_baseline_deviation():
    sr = 8000.0
    analyzer = AcousticAnalyzer(
        sample_rate=sr,
        window_seconds=1.0,
        overlap=0.0,
        baseline=AcousticBaseline(feature_stats={"rms": (0.1, 0.05)}),
    )
    signal = _sine(500.0, sr, n=16000, amplitude=0.3)
    chunk = SampleChunk(samples=signal, sample_rate=sr, timestamp=datetime.now(timezone.utc))

    evidence = analyzer.process_chunk(chunk, "test")

    assert len(evidence) == 2
    assert "rms" in evidence[0].baseline_deviation


def test_live_microphone_reports_not_connected():
    mic = LiveMicrophone(device_id="mic-0")
    assert mic.is_live is True
    with pytest.raises(ConnectionError):
        mic.open()


def _find_first_real_wav() -> str | None:
    for name in ("bearing/bearing/test", "fan/fan/test"):
        candidates = sorted((settings.dataset_dir / name).glob("*.wav")) if (settings.dataset_dir / name).is_dir() else []
        if candidates:
            return str(candidates[0])
    return None


@pytest.mark.skipif(not settings.dataset_dir.is_dir(), reason="DATASET/ not present in this environment")
def test_audio_file_reader_streams_real_wav():
    wav_path = _find_first_real_wav()
    if wav_path is None:
        pytest.skip("no real WAV file found to test against")

    reader = AudioFileReader(wav_path)
    with reader:
        assert reader.is_live is False
        assert reader.sample_rate == 16000.0

        chunk = reader.read_chunk(8000)
        assert chunk is not None
        assert len(chunk.samples) == 8000
        assert np.max(np.abs(chunk.samples)) <= 1.0 + 1e-6  # normalized

        analyzer = AcousticAnalyzer(sample_rate=reader.sample_rate, window_seconds=0.5, overlap=0.0)
        evidence = analyzer.process_chunk(chunk, reader.source_description)
        assert len(evidence) >= 1
        assert evidence[0].features.rms >= 0
