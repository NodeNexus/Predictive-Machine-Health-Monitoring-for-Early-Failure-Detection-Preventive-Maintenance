"""Acoustic window feature extraction.

Reuses the same octave/1-3-octave module as the vibration pipeline
(app.pipelines.common.octave) so both modalities produce identically
structured band data regardless of sample rate.
"""
from __future__ import annotations

import librosa
import numpy as np
from pydantic import BaseModel

from app.pipelines.common.octave import BandAnalysisResult, BandType, compute_band_energies


class AcousticSpectralPeak(BaseModel):
    frequency: float
    magnitude: float


class AcousticFeatures(BaseModel):
    # time / level domain
    rms: float
    peak_amplitude: float
    crest_factor: float
    energy: float

    # frequency domain
    dominant_frequency: float
    spectral_centroid: float
    spectral_bandwidth: float
    spectral_rolloff: float
    spectral_flatness: float
    spectral_peaks: list[AcousticSpectralPeak]

    # bands
    band_energies: BandAnalysisResult

    # learned/cepstral
    mfcc: list[float]


def extract_acoustic_features(
    window: np.ndarray,
    sample_rate: float,
    n_peaks: int = 5,
    band_type: BandType = "octave",
    n_mfcc: int = 13,
    fft_size: int = 2048,
    hop_length: int = 512,
) -> AcousticFeatures:
    n = len(window)
    peak_amplitude = float(np.max(np.abs(window)))
    rms = float(np.sqrt(np.mean(np.square(window))))
    crest_factor = peak_amplitude / rms if rms > 0 else 0.0
    energy = float(np.sum(np.square(window)))

    detrended = window - np.mean(window)
    windowed = detrended * np.hanning(n)
    spectrum = np.fft.rfft(windowed)
    magnitude = np.abs(spectrum)
    power = magnitude**2
    freqs = np.fft.rfftfreq(n, d=1 / sample_rate)

    search_magnitude = magnitude.copy()
    search_magnitude[0] = 0.0
    dominant_frequency = float(freqs[int(np.argmax(search_magnitude))])

    total_magnitude = np.sum(magnitude[1:])
    if total_magnitude > 0:
        spectral_centroid = float(np.sum(freqs[1:] * magnitude[1:]) / total_magnitude)
        spectral_bandwidth = float(
            np.sqrt(np.sum(((freqs[1:] - spectral_centroid) ** 2) * magnitude[1:]) / total_magnitude)
        )
        cumulative = np.cumsum(magnitude[1:])
        rolloff_idx = int(np.searchsorted(cumulative, 0.85 * cumulative[-1]))
        spectral_rolloff = float(freqs[1:][min(rolloff_idx, len(freqs) - 2)])
    else:
        spectral_centroid = spectral_bandwidth = spectral_rolloff = 0.0

    # Flatness: ratio of geometric mean to arithmetic mean of the power
    # spectrum - near 1.0 for noise-like signals, near 0 for tonal ones.
    positive_power = power[1:]
    positive_power = positive_power[positive_power > 0]
    if len(positive_power) > 0:
        geometric_mean = float(np.exp(np.mean(np.log(positive_power))))
        arithmetic_mean = float(np.mean(positive_power))
        spectral_flatness = geometric_mean / arithmetic_mean if arithmetic_mean > 0 else 0.0
    else:
        spectral_flatness = 0.0

    peak_indices = np.argsort(search_magnitude)[-n_peaks:][::-1]
    spectral_peaks = [
        AcousticSpectralPeak(frequency=float(freqs[i]), magnitude=float(magnitude[i])) for i in peak_indices
    ]

    band_energies = compute_band_energies(freqs, power, band_type=band_type, fmin=20.0)

    n_fft_actual = min(fft_size, n)
    mfcc_matrix = librosa.feature.mfcc(
        y=window.astype(np.float32),
        sr=sample_rate,
        n_mfcc=n_mfcc,
        n_fft=n_fft_actual,
        hop_length=min(hop_length, n_fft_actual),
    )
    mfcc = mfcc_matrix.mean(axis=1).tolist()  # average across STFT frames within this window

    return AcousticFeatures(
        rms=rms,
        peak_amplitude=peak_amplitude,
        crest_factor=crest_factor,
        energy=energy,
        dominant_frequency=dominant_frequency,
        spectral_centroid=spectral_centroid,
        spectral_bandwidth=spectral_bandwidth,
        spectral_rolloff=spectral_rolloff,
        spectral_flatness=spectral_flatness,
        spectral_peaks=spectral_peaks,
        band_energies=band_energies,
        mfcc=mfcc,
    )


def compute_stft(window: np.ndarray, fft_size: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Returns the magnitude STFT, kept separate from AcousticFeatures so
    dashboard telemetry doesn't have to carry a full spectrogram matrix on
    every push - callers that need it for ML dataset-building or a
    dedicated spectrogram panel call this directly."""
    n_fft_actual = min(fft_size, len(window))
    stft = librosa.stft(window.astype(np.float32), n_fft=n_fft_actual, hop_length=min(hop_length, n_fft_actual))
    return np.abs(stft)
