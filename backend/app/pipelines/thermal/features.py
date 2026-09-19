"""Thermal frame feature extraction.

Operates on intensity (grayscale) values. Since none of the current demo
videos carry radiometric calibration, all "intensity" values are relative
brightness, not degrees - callers must not present them as °C unless
`ThermalFrame.is_radiometric` is True.
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel


class ThermalFeatures(BaseModel):
    mean_intensity: float
    max_intensity: float
    min_intensity: float
    std_intensity: float
    hotspot_threshold: float
    hotspot_pixel_count: int
    hotspot_area_fraction: float
    hotspot_centroid_x: float | None = None
    hotspot_centroid_y: float | None = None
    gradient_mean: float
    gradient_max: float
    is_radiometric: bool = False


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.astype(np.float64)
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float64)
    raise ValueError(f"Unsupported thermal frame shape: {image.shape}")


def extract_thermal_features(
    image: np.ndarray,
    hotspot_percentile: float = 99.0,
    is_radiometric: bool = False,
    roi: tuple[int, int, int, int] | None = None,  # (x, y, w, h)
) -> ThermalFeatures:
    """Extract statistical/spatial features from one thermal frame.

    `roi` restricts analysis to a sub-region (machine area) when set;
    otherwise the whole frame is analyzed.
    """
    gray = _to_grayscale(image)
    if roi is not None:
        x, y, w, h = roi
        gray = gray[y : y + h, x : x + w]

    if gray.size == 0:
        raise ValueError("Empty region for thermal feature extraction (check ROI bounds)")

    mean_intensity = float(np.mean(gray))
    max_intensity = float(np.max(gray))
    min_intensity = float(np.min(gray))
    std_intensity = float(np.std(gray))

    threshold = float(np.percentile(gray, hotspot_percentile))
    # Strict '>' rather than '>=': when the background is uniform (or has a
    # dominant repeated value), the percentile itself can land exactly on
    # that background value, which would otherwise flag the entire frame.
    hotspot_mask = gray > threshold
    hotspot_pixel_count = int(np.count_nonzero(hotspot_mask))
    hotspot_area_fraction = hotspot_pixel_count / gray.size

    centroid_x: float | None = None
    centroid_y: float | None = None
    if hotspot_pixel_count > 0:
        ys, xs = np.nonzero(hotspot_mask)
        centroid_x = float(np.mean(xs))
        centroid_y = float(np.mean(ys))

    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.hypot(grad_x, grad_y)

    return ThermalFeatures(
        mean_intensity=mean_intensity,
        max_intensity=max_intensity,
        min_intensity=min_intensity,
        std_intensity=std_intensity,
        hotspot_threshold=threshold,
        hotspot_pixel_count=hotspot_pixel_count,
        hotspot_area_fraction=hotspot_area_fraction,
        hotspot_centroid_x=centroid_x,
        hotspot_centroid_y=centroid_y,
        gradient_mean=float(np.mean(gradient_magnitude)),
        gradient_max=float(np.max(gradient_magnitude)),
        is_radiometric=is_radiometric,
    )
