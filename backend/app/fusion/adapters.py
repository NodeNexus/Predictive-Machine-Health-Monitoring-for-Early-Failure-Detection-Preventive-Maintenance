"""Flattens each modality's rich Pydantic feature model into a scalar
dict[str, float] for baseline/anomaly/fusion consumption.

Kept separate from the feature-extraction modules themselves, since this
is a fusion-layer concern (which scalar features feed the baseline/
Isolation Forest), not a property of the features themselves.
"""
from __future__ import annotations

from app.pipelines.acoustic.features import AcousticFeatures
from app.pipelines.thermal.features import ThermalFeatures
from app.pipelines.vibration.features import VibrationFeatures

THERMAL_BASELINE_FEATURES = [
    "mean_intensity",
    "max_intensity",
    "std_intensity",
    "hotspot_area_fraction",
    "gradient_mean",
]

VIBRATION_BASELINE_FEATURES = [
    "rms",
    "std",
    "crest_factor",
    "kurtosis",
    "skewness",
    "spectral_centroid",
]

ACOUSTIC_BASELINE_FEATURES = [
    "rms",
    "crest_factor",
    "spectral_centroid",
    "spectral_bandwidth",
    "spectral_flatness",
]


def thermal_feature_dict(features: ThermalFeatures) -> dict[str, float]:
    return {name: getattr(features, name) for name in THERMAL_BASELINE_FEATURES}


def vibration_feature_dict(features: VibrationFeatures) -> dict[str, float]:
    return {name: getattr(features, name) for name in VIBRATION_BASELINE_FEATURES}


def acoustic_feature_dict(features: AcousticFeatures) -> dict[str, float]:
    result = {name: getattr(features, name) for name in ACOUSTIC_BASELINE_FEATURES}
    for i, value in enumerate(features.mfcc[:5]):
        result[f"mfcc_{i}"] = value
    return result
