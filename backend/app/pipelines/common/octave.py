"""Reusable octave / 1/3-octave band-energy computation.

Shared by the vibration and acoustic pipelines so both use identical
band-analysis semantics regardless of sample rate or machine. Center
frequencies follow the standard ISO/ANSI base-2 series referenced to 1kHz
(f_c = 1000 * 2^k for octave, 1000 * 2^(k/3) for 1/3-octave), which matches
the conventional preferred frequencies (31.5, 63, 125, ... Hz) to within
normal rounding.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel

BandType = Literal["octave", "third_octave"]


class BandEnergy(BaseModel):
    center_frequency: float
    low_frequency: float
    high_frequency: float
    energy: float


class BandAnalysisResult(BaseModel):
    band_type: BandType
    bands: list[BandEnergy]


def _band_centers(band_type: BandType, fmin: float, fmax: float) -> list[float]:
    """All band centers (referenced to 1kHz) whose band overlaps [fmin, fmax]."""
    step = 1.0 if band_type == "octave" else 1.0 / 3.0
    edge_ratio = 2 ** (0.5 * step)
    bands_per_decade_span = int(round(np.log2(20000 / 1) / step)) + 2  # generous bound, e.g. ~15kHz range

    centers: list[float] = []
    for k in range(-bands_per_decade_span, bands_per_decade_span + 1):
        center = 1000 * 2 ** (k * step)
        low, high = center / edge_ratio, center * edge_ratio
        if high > fmin and low < fmax:
            centers.append(center)
    return sorted(centers)


def compute_band_energies(
    freqs: np.ndarray,
    power_spectrum: np.ndarray,
    band_type: BandType = "octave",
    fmin: float = 20.0,
    fmax: float | None = None,
) -> BandAnalysisResult:
    """Aggregate a power spectrum into octave or 1/3-octave bands.

    `freqs` and `power_spectrum` must be equal-length 1-D arrays (e.g. from
    `np.fft.rfftfreq` / `|rfft|**2`). Bands entirely above the Nyquist
    frequency are naturally excluded since `fmax` defaults to it.
    """
    nyquist = float(freqs[-1]) if len(freqs) else 0.0
    fmax = min(fmax, nyquist) if fmax is not None else nyquist

    step = 1.0 if band_type == "octave" else 1.0 / 3.0
    edge_ratio = 2 ** (0.5 * step)

    bands: list[BandEnergy] = []
    for center in _band_centers(band_type, fmin, fmax):
        low = center / edge_ratio
        high = center * edge_ratio
        mask = (freqs >= low) & (freqs < high)
        energy = float(np.sum(power_spectrum[mask])) if np.any(mask) else 0.0
        bands.append(BandEnergy(center_frequency=center, low_frequency=low, high_frequency=high, energy=energy))

    return BandAnalysisResult(band_type=band_type, bands=bands)
