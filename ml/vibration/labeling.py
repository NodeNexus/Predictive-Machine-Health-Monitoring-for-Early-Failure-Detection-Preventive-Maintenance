"""Derives vibration health labels from the IMS 1st_test/channel 4
run-to-failure trajectory.

CRITICAL, stated once here and repeated everywhere this label is used:
the IMS dataset provides NO per-file ground-truth anomaly/severity label.
The vendor documentation states only that "inner race defect occurred in
bearing 3" BY THE END of the ~36-day run. Every label produced by this
module is DERIVED from a documented statistical rule applied to the
dataset's own early "known-healthy" period - it is not, and must never be
described as, original dataset ground truth.

Rule (documented, reproducible, derived from a full-trajectory scan of all
2156 files in this task - NOT assumed from prior sparse sampling):
  1. A baseline period (files [0, BASELINE_END)) is used to compute the
     mean/std of RMS and kurtosis - independently re-verified flat in this
     task's full scan (rms std=0.00074 relative to mean=0.1311).
  2. For every file, z_rms and z_kurtosis are computed against that
     baseline.
  3. CRITICAL EMPIRICAL FINDING that shaped this rule: RMS is NOT a good
     severity-graduation signal past the initial fault onset - z_rms jumps
     from ~0-2 to ~35-65 within ~50 files of the onset (file ~156) and
     STAYS in that saturated range for the rest of the 2000-file run. Using
     max(z_rms, z_kurtosis) (an earlier, rejected version of this rule)
     collapses 2000/2156 files into "severe" and leaves "degrading" with
     only 3 transient single-file blips - not a usable label.
     Kurtosis, in contrast, stays near-baseline (z mostly 0-8, occasional
     blips to ~15) through the elevated-but-stable plateau (files ~156-
     ~1850), then rises sharply and sustainedly from file ~1900 onward
     (z=39, 117, 161 observed) - a real, physically meaningful change in
     impulsiveness consistent with late-stage bearing spalling, not noise.
  4. Rule: healthy = z_rms below threshold; severe = z_kurtosis at/above
     threshold (regardless of z_rms, since RMS is already saturated by
     then); degrading = everything in between (RMS elevated, kurtosis
     still near-baseline). Both thresholds reuse this codebase's existing
     z-score conventions (anomaly_z_threshold=3.0, fusion's
     severity_z_cap=10.0) for internal consistency, not tuned to this
     specific file range.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BASELINE_END_INDEX = 100  # files [0, 100) - independently re-verified flat in this task
HEALTHY_Z_THRESHOLD = 3.0  # matches app.core.config.settings.anomaly_z_threshold
SEVERE_Z_THRESHOLD = 10.0  # matches app.fusion.engine.FusionEngine's severity_z_cap


@dataclass
class BaselineStats:
    rms_mean: float
    rms_std: float
    kurtosis_mean: float
    kurtosis_std: float
    baseline_end_index: int


def compute_baseline(records: list[dict], baseline_end_index: int = BASELINE_END_INDEX) -> BaselineStats:
    baseline = records[:baseline_end_index]
    rms = np.array([r["rms"] for r in baseline])
    kurtosis = np.array([r["kurtosis"] for r in baseline])
    return BaselineStats(
        rms_mean=float(rms.mean()),
        rms_std=float(rms.std()),
        kurtosis_mean=float(kurtosis.mean()),
        kurtosis_std=float(kurtosis.std()),
        baseline_end_index=baseline_end_index,
    )


def z_scores(record: dict, baseline: BaselineStats) -> tuple[float, float]:
    z_rms = (record["rms"] - baseline.rms_mean) / baseline.rms_std if baseline.rms_std > 0 else 0.0
    z_kurt = (record["kurtosis"] - baseline.kurtosis_mean) / baseline.kurtosis_std if baseline.kurtosis_std > 0 else 0.0
    return z_rms, z_kurt


def label_3class(z_rms: float, z_kurtosis: float) -> str:
    """healthy: RMS not yet elevated. severe: kurtosis (impulsiveness) has
    escalated, regardless of RMS (which saturates early and stops being
    informative). degrading: RMS elevated but kurtosis still near baseline -
    the genuinely intermediate physical state."""
    if z_rms < HEALTHY_Z_THRESHOLD:
        return "healthy"
    if z_kurtosis >= SEVERE_Z_THRESHOLD:
        return "severe"
    return "degrading"


def label_binary(z_rms: float, z_kurtosis: float) -> str:
    return "normal" if (z_rms < HEALTHY_Z_THRESHOLD and z_kurtosis < HEALTHY_Z_THRESHOLD) else "degraded"


def health_index_from_z(z_rms: float, z_kurtosis: float, cap: float = SEVERE_Z_THRESHOLD) -> float:
    """Continuous 0-100 health index (100=baseline-like, 0=at or beyond the
    severe kurtosis threshold). Deterministic rescaling of max(z_rms, z_kurtosis)."""
    severity = max(z_rms, z_kurtosis)
    return float(max(0.0, 100.0 * (1 - min(severity, cap) / cap)))


def build_labeled_records(records: list[dict], baseline_end_index: int = BASELINE_END_INDEX) -> tuple[list[dict], BaselineStats]:
    baseline = compute_baseline(records, baseline_end_index)
    labeled = []
    for r in records:
        z_rms, z_kurt = z_scores(r, baseline)
        labeled.append(
            {
                **r,
                "z_rms": z_rms,
                "z_kurtosis": z_kurt,
                "label_3class": label_3class(z_rms, z_kurt),
                "label_binary": label_binary(z_rms, z_kurt),
                "health_index": health_index_from_z(z_rms, z_kurt),
            }
        )
    return labeled, baseline
