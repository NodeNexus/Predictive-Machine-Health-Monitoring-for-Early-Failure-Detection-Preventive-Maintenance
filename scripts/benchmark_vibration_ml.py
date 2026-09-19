#!/usr/bin/env python
"""VIBRATION ML V1 LIVE INTEGRATION - step 6: real runtime performance
benchmark. Measures actual latency on real IMS channel-4 windows (not
extrapolated from thermal), matching the deterministic + ML pipeline order
used by demo_runner._vibration_loop.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from app.pipelines.vibration.features import extract_vibration_features  # noqa: E402
from app.pipelines.vibration.ml_model import VibrationMLModel  # noqa: E402

IMS_DIR = REPO_ROOT / "DATASET" / "IMS" / "IMS" / "1st_test" / "1st_test"
CHANNEL = 4
SAMPLE_RATE = 20000.0
N_WINDOWS = 100


def main() -> None:
    files = sorted(IMS_DIR.iterdir())[:N_WINDOWS]
    if not files:
        print(f"No IMS files found under {IMS_DIR}")
        raise SystemExit(1)

    windows = [np.loadtxt(f)[:, CHANNEL] for f in files]

    model = VibrationMLModel()
    if not model.available:
        print("WARNING: vibration ML model unavailable - only deterministic timing will be measured.")

    try:
        import psutil

        process = psutil.Process()
        process.cpu_percent(interval=None)  # prime the measurement
        cpu_available = True
    except ImportError:
        cpu_available = False
        print("psutil not installed - skipping CPU usage measurement.")

    feature_times = []
    ml_times = []
    total_times = []

    for window in windows:
        t0 = time.perf_counter()
        features = extract_vibration_features(window, sample_rate=SAMPLE_RATE)
        t1 = time.perf_counter()
        model.predict(features)
        t2 = time.perf_counter()

        feature_times.append(t1 - t0)
        ml_times.append(t2 - t1)
        total_times.append(t2 - t0)

    cpu_percent = process.cpu_percent(interval=None) if cpu_available else None

    def stats(name: str, values: list[float]) -> dict:
        arr = np.array(values) * 1000.0  # ms
        return {
            "mean_ms": float(arr.mean()),
            "p95_ms": float(np.percentile(arr, 95)),
            "max_ms": float(arr.max()),
        }

    feature_stats = stats("feature_extraction", feature_times)
    ml_stats = stats("ml_inference", ml_times)
    total_stats = stats("total_vibration_cycle", total_times)
    mean_total_s = np.mean(total_times)
    fps = 1.0 / mean_total_s if mean_total_s > 0 else float("inf")

    print(f"Benchmarked {len(windows)} real IMS channel-{CHANNEL} windows (20,480 samples each, 20kHz)")
    print(f"Feature extraction: {feature_stats}")
    print(f"ML inference:        {ml_stats}")
    print(f"Total cycle:         {total_stats}")
    print(f"Effective processing rate: {fps:.1f} windows/sec")
    print(f"CPU usage during benchmark: {cpu_percent}%" if cpu_available else "CPU usage: not measured (psutil unavailable)")

    result = {
        "n_windows": len(windows),
        "channel": CHANNEL,
        "window_samples": 20480,
        "sample_rate": SAMPLE_RATE,
        "model_available": model.available,
        "feature_extraction_ms": feature_stats,
        "ml_inference_ms": ml_stats,
        "total_vibration_cycle_ms": total_stats,
        "effective_windows_per_second": float(fps),
        "cpu_percent_during_benchmark": cpu_percent,
        "note": "Measured directly, not extrapolated from thermal ML performance. "
        "This is a tabular RandomForest on a 10-feature vector, not an image CNN.",
    }
    out_path = REPO_ROOT / "models" / "vibration" / "runtime_benchmark.json"
    import json

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
