"""Runtime wrapper around the trained Acoustic ML V1 classifier
(models/acoustic/acoustic_baseline_v1.joblib).

IMPORTANT INTEGRATION FINDING (discovered during this task, not assumed):
Acoustic ML V1 was trained on WHOLE-10-SECOND-CLIP feature vectors - each
of the 61 trained feature columns (temporal, spectral, 10 octave bands,
27 third-octave bands, 13 MFCCs) was computed once per full WAV file (see
ml/acoustic/dataset.py). The live AcousticAnalyzer, by contrast, computes
features over much shorter sliding windows
(app.core.config.settings.audio_window_seconds = 1.0s, 10x shorter than a
clip) and only ONE band family per session (settings.octave_mode is a
single global choice - "octave" OR "third_octave", never both). Feeding
the analyzer's per-window evidence into this model would violate the
input distribution it was trained on (amplitude/energy-scaled features
would be systematically off by roughly the window/clip length ratio) AND
would be missing half the trained feature columns outright (whichever
band family settings.octave_mode didn't select).

Rather than papering over this with zero-filled missing columns (which
would silently corrupt predictions) or feeding mismatched short-window
features into a clip-trained model, this component reproduces the exact
training-time unit of analysis: it loads and featurizes the FULL demo
audio file directly - reusing app.pipelines.acoustic.features.
extract_acoustic_features UNMODIFIED, called twice (band_type="octave"
and band_type="third_octave"), exactly as ml/acoustic/dataset.py already
does for training - at the point each demo playback file is opened,
rather than hooking into AcousticAnalyzer's per-window streaming evidence.
No FFT/STFT/MFCC/octave logic is reimplemented; the existing function is
simply called at the clip granularity it was trained on.

This means: ONE ML prediction is produced per file play / loop-around
(the whole clip), not one per streaming window - this is the model's true
granularity, not an approximation. The deterministic, per-window
AcousticAnalyzer output is completely untouched and continues to feed
baseline/anomaly/health/fusion exactly as before; this module's output is
ADDITIVE evidence only.

Loads the model exactly once per demo session. If the model/metadata files
are missing or inference raises for any reason, `.available` is False (or
the failing call returns None) and the caller is expected to degrade
gracefully - never let an ML failure interrupt the deterministic acoustic
loop or crash the demo.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("acoustic.ml_model")

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "acoustic" / "acoustic_baseline_v1.joblib"
DEFAULT_METADATA_PATH = REPO_ROOT / "models" / "acoustic" / "model_metadata.json"


def _load_whole_clip(path: Path) -> tuple[np.ndarray, float]:
    """Reads an ENTIRE WAV file, normalized to [-1, 1] - the same
    convention app.pipelines.acoustic.readers.AudioFileReader uses.
    Multi-channel files are downmixed to mono by averaging, matching the
    reader's behavior."""
    with wave.open(str(path), "rb") as wf:
        sample_rate = float(wf.getframerate())
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sampwidth]
    data = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    max_val = float(np.iinfo(dtype).max) if dtype != np.uint8 else 127.5
    offset = 128.0 if dtype == np.uint8 else 0.0
    normalized = (data - offset) / max_val
    return normalized, sample_rate


class AcousticMLModel:
    """Loads once; call `.predict(file_path)` once per demo clip play
    (see module docstring for why this is per-clip, not per-window)."""

    def __init__(self, model_path: Path = DEFAULT_MODEL_PATH, metadata_path: Path = DEFAULT_METADATA_PATH) -> None:
        self.available = False
        self.class_names: list[str] = []
        self.feature_columns: list[str] = []
        self.model_version: str | None = None
        self._model = None
        self._scaler = None

        try:
            import json

            import joblib

            if not model_path.is_file():
                raise FileNotFoundError(f"Acoustic ML model not found: {model_path}")
            if not metadata_path.is_file():
                raise FileNotFoundError(f"Acoustic ML metadata not found: {metadata_path}")

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.class_names = metadata["class_names"]
            self.feature_columns = metadata["feature_columns"]
            self.model_version = metadata["model_version"]

            bundle = joblib.load(model_path)
            self._model = bundle["model"]
            self._scaler = bundle.get("scaler")  # present for the exported logistic_regression

            self.available = True
            logger.info(f"Acoustic ML model loaded ({self.model_version}, classes={self.class_names})")
        except Exception as exc:  # noqa: BLE001 - any failure here must not be fatal
            logger.warning(f"Acoustic ML model unavailable, continuing without it: {exc}")

    def _extract_feature_vector(self, window: np.ndarray, sample_rate: float) -> dict:
        from app.pipelines.acoustic.features import extract_acoustic_features

        octave_features = extract_acoustic_features(window, sample_rate=sample_rate, band_type="octave")
        third_octave_features = extract_acoustic_features(window, sample_rate=sample_rate, band_type="third_octave")

        flat = {
            "rms": octave_features.rms,
            "peak_amplitude": octave_features.peak_amplitude,
            "crest_factor": octave_features.crest_factor,
            "energy": octave_features.energy,
            "dominant_frequency": octave_features.dominant_frequency,
            "spectral_centroid": octave_features.spectral_centroid,
            "spectral_bandwidth": octave_features.spectral_bandwidth,
            "spectral_rolloff": octave_features.spectral_rolloff,
            "spectral_flatness": octave_features.spectral_flatness,
            "top_spectral_peak_frequency": octave_features.spectral_peaks[0].frequency if octave_features.spectral_peaks else 0.0,
            "top_spectral_peak_magnitude": octave_features.spectral_peaks[0].magnitude if octave_features.spectral_peaks else 0.0,
        }
        for i, band in enumerate(octave_features.band_energies.bands):
            flat[f"octave_band_{i}"] = band.energy
        for i, band in enumerate(third_octave_features.band_energies.bands):
            flat[f"third_octave_band_{i}"] = band.energy
        for i, coeff in enumerate(octave_features.mfcc):
            flat[f"mfcc_{i}"] = coeff
        return flat

    def predict(self, file_path: Path) -> dict | None:
        """`file_path` is the demo's whole audio source file - featurized
        fresh here (reusing extract_acoustic_features, not reimplemented)
        at the exact training-time unit of analysis. Returns a raw
        prediction dict, or None if the model isn't available, the file
        can't be read, the feature set doesn't match what the model
        expects, or inference fails for any reason - never raises."""
        if not self.available:
            return None
        try:
            window, sample_rate = _load_whole_clip(Path(file_path))
            feature_values = self._extract_feature_vector(window, sample_rate)
            row = [feature_values[col] for col in self.feature_columns]
            X = np.array([row], dtype=np.float64)
            if self._scaler is not None:
                X = self._scaler.transform(X)

            probs = self._model.predict_proba(X)[0]
            top_idx = int(np.argmax(probs))
            return {
                "predicted_class": self.class_names[top_idx],
                "confidence": float(probs[top_idx]),
                "probabilities": {name: float(p) for name, p in zip(self.class_names, probs)},
                "model_version": self.model_version,
            }
        except Exception as exc:  # noqa: BLE001 - inference/feature-mismatch failure must not crash the caller
            logger.warning(f"Acoustic ML inference failed on {file_path}, skipping: {exc}")
            return None
