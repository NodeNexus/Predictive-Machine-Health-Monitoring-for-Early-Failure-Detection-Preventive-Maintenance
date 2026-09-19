import numpy as np

from app.pipelines.common.octave import compute_band_energies


def test_octave_bands_cover_standard_range():
    freqs = np.linspace(0, 20000, 4096)
    power = np.ones_like(freqs)
    result = compute_band_energies(freqs, power, band_type="octave", fmin=20, fmax=20000)
    centers = [round(b.center_frequency) for b in result.bands]
    # standard ISO preferred octave centers (approx, base-2 referenced to 1kHz)
    assert 1000 in centers
    assert 2000 in centers
    assert 500 in centers
    assert centers == sorted(centers)


def test_band_energy_isolates_a_pure_tone():
    sample_rate = 16000
    n = 16000
    t = np.arange(n) / sample_rate
    signal = np.sin(2 * np.pi * 1000 * t)  # pure 1kHz tone
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    freqs = np.fft.rfftfreq(n, d=1 / sample_rate)

    result = compute_band_energies(freqs, spectrum, band_type="octave", fmin=20, fmax=8000)
    band_1000 = next(b for b in result.bands if round(b.center_frequency) == 1000)
    other_bands = [b for b in result.bands if round(b.center_frequency) != 1000]

    assert band_1000.energy > sum(b.energy for b in other_bands)


def test_third_octave_has_more_bands_than_octave_over_same_range():
    freqs = np.linspace(0, 4000, 2048)
    power = np.ones_like(freqs)
    octave = compute_band_energies(freqs, power, band_type="octave", fmin=20, fmax=4000)
    third = compute_band_energies(freqs, power, band_type="third_octave", fmin=20, fmax=4000)
    assert len(third.bands) > len(octave.bands)
