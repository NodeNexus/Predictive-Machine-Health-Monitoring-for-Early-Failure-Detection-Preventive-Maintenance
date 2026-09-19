"""Vibration window feature extraction.

Bearing characteristic frequencies (BPFO/BPFI/BSF/FTF) are only computed
when the caller actually supplies RPM *and* bearing geometry - never
inferred or assumed. Without them, the result is labelled explicitly as
generic spectral analysis.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel
from scipy import stats

from app.pipelines.common.octave import BandAnalysisResult, BandType, compute_band_energies


class SpectralPeak(BaseModel):
    frequency: float
    magnitude: float


class BearingGeometry(BaseModel):
    n_balls: int
    ball_diameter_mm: float
    pitch_diameter_mm: float
    contact_angle_deg: float = 0.0


class BearingFaultFrequencies(BaseModel):
    bpfo: float  # ball pass frequency, outer race
    bpfi: float  # ball pass frequency, inner race
    bsf: float  # ball spin frequency
    ftf: float  # fundamental train (cage) frequency


class VibrationFeatures(BaseModel):
    # time domain
    rms: float
    variance: float
    std: float
    peak: float
    peak_to_peak: float
    crest_factor: float
    kurtosis: float
    skewness: float

    # frequency domain
    dominant_frequency: float
    spectral_centroid: float
    spectral_bandwidth: float
    spectral_peaks: list[SpectralPeak]
    band_energies: BandAnalysisResult | None = None

    analysis_type: Literal["generic_spectral", "bearing_specific"] = "generic_spectral"
    bearing_fault_frequencies: BearingFaultFrequencies | None = None


def extract_time_domain_features(window: np.ndarray) -> dict:
    peak = float(np.max(np.abs(window)))
    rms = float(np.sqrt(np.mean(np.square(window))))
    return {
        "rms": rms,
        "variance": float(np.var(window)),
        "std": float(np.std(window)),
        "peak": peak,
        "peak_to_peak": float(np.max(window) - np.min(window)),
        "crest_factor": peak / rms if rms > 0 else 0.0,
        "kurtosis": float(stats.kurtosis(window, fisher=False)) if len(window) > 3 else 0.0,
        "skewness": float(stats.skew(window)) if len(window) > 2 else 0.0,
    }


def extract_frequency_domain_features(
    window: np.ndarray,
    sample_rate: float,
    n_peaks: int = 5,
    band_type: BandType = "octave",
) -> dict:
    n = len(window)
    detrended = window - np.mean(window)  # remove DC/sensor-bias so it can't dominate the spectrum
    windowed = detrended * np.hanning(n)
    spectrum = np.fft.rfft(windowed)
    magnitude = np.abs(spectrum)
    power = magnitude**2
    freqs = np.fft.rfftfreq(n, d=1 / sample_rate)

    # Bin 0 (0 Hz) carries only residual DC leakage after detrending, never
    # a real "dominant vibration frequency" - exclude it from peak search.
    search_magnitude = magnitude.copy()
    search_magnitude[0] = 0.0

    dominant_idx = int(np.argmax(search_magnitude))
    dominant_frequency = float(freqs[dominant_idx])

    total_magnitude = np.sum(magnitude[1:])
    spectral_centroid = (
        float(np.sum(freqs[1:] * magnitude[1:]) / total_magnitude) if total_magnitude > 0 else 0.0
    )
    spectral_bandwidth = (
        float(np.sqrt(np.sum(((freqs[1:] - spectral_centroid) ** 2) * magnitude[1:]) / total_magnitude))
        if total_magnitude > 0
        else 0.0
    )

    peak_indices = np.argsort(search_magnitude)[-n_peaks:][::-1]
    spectral_peaks = [
        SpectralPeak(frequency=float(freqs[i]), magnitude=float(magnitude[i])) for i in peak_indices
    ]

    band_energies = compute_band_energies(freqs, power, band_type=band_type, fmin=1.0)

    return {
        "dominant_frequency": dominant_frequency,
        "spectral_centroid": spectral_centroid,
        "spectral_bandwidth": spectral_bandwidth,
        "spectral_peaks": spectral_peaks,
        "band_energies": band_energies,
    }


def compute_bearing_fault_frequencies(rpm: float, geometry: BearingGeometry) -> BearingFaultFrequencies:
    """Standard rolling-element bearing fault frequency formulas.

    fr = shaft rotation frequency (Hz); n = number of balls; d = ball
    diameter; D = pitch diameter; phi = contact angle.
    """
    fr = rpm / 60.0
    n = geometry.n_balls
    ratio = geometry.ball_diameter_mm / geometry.pitch_diameter_mm
    phi_rad = np.radians(geometry.contact_angle_deg)
    cos_phi = np.cos(phi_rad)

    bpfo = (n / 2) * fr * (1 - ratio * cos_phi)
    bpfi = (n / 2) * fr * (1 + ratio * cos_phi)
    bsf = (geometry.pitch_diameter_mm / (2 * geometry.ball_diameter_mm)) * fr * (1 - (ratio * cos_phi) ** 2)
    ftf = (fr / 2) * (1 - ratio * cos_phi)

    return BearingFaultFrequencies(bpfo=float(bpfo), bpfi=float(bpfi), bsf=float(bsf), ftf=float(ftf))


def extract_vibration_features(
    window: np.ndarray,
    sample_rate: float,
    rpm: float | None = None,
    bearing_geometry: BearingGeometry | None = None,
    band_type: BandType = "octave",
    n_peaks: int = 5,
) -> VibrationFeatures:
    time_features = extract_time_domain_features(window)
    freq_features = extract_frequency_domain_features(window, sample_rate, n_peaks=n_peaks, band_type=band_type)

    bearing_frequencies: BearingFaultFrequencies | None = None
    analysis_type: Literal["generic_spectral", "bearing_specific"] = "generic_spectral"
    if rpm is not None and bearing_geometry is not None:
        bearing_frequencies = compute_bearing_fault_frequencies(rpm, bearing_geometry)
        analysis_type = "bearing_specific"

    return VibrationFeatures(
        **time_features,
        **freq_features,
        analysis_type=analysis_type,
        bearing_fault_frequencies=bearing_frequencies,
    )
