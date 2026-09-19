#!/usr/bin/env python
"""ACOUSTIC ML V1 LIVE INTEGRATION - step 4: real runtime performance
benchmark. Measures actual latency on real bearing WAV files (not
extrapolated from thermal/vibration), matching the two DIFFERENT
granularities actually used at runtime:
  - deterministic feature extraction: per 1-second sliding window
    (matches AcousticAnalyzer's real per-window cost)
  - ML inference: per WHOLE 10-second clip, once per file play/loop-around
    (matches AcousticMLModel's real per-clip cost - see its docstring for
    why this is clip-granularity, not window-granularity)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings  # noqa: E402
from app.pipelines.acoustic.features import extract_acoustic_features  # noqa: E402
from app.pipelines.acoustic.ml_model import AcousticMLModel, _load_whole_clip  # noqa: E402

DATASET_DIR = REPO_ROOT / "DATASET" / "bearing" / "bearing"
N_FILES = 40


def main() -> None:
    files = sorted((DATASET_DIR / "test").glob("*.wav"))[:N_FILES]
    if not files:
        print(f"No WAV files found under {DATASET_DIR / 'test'}")
        raise SystemExit(1)

    model = AcousticMLModel()
    if not model.available:
        print("WARNING: acoustic ML model unavailable - only deterministic timing will be measured.")

    window_seconds = settings.audio_window_seconds
    window_extraction_times = []
    ml_inference_times = []
    combined_worst_case_times = []

    for f in files:
        window, sample_rate = _load_whole_clip(f)
        window_1s = window[: int(sample_rate * window_seconds)]

        t0 = time.perf_counter()
        extract_acoustic_features(window_1s, sample_rate=sample_rate, band_type=settings.octave_mode,
                                   n_mfcc=settings.mfcc_n_coeffs, fft_size=settings.fft_size, hop_length=settings.stft_hop)
        t1 = time.perf_counter()
        window_extraction_times.append(t1 - t0)

        t2 = time.perf_counter()
        model.predict(f)
        t3 = time.perf_counter()
        ml_inference_times.append(t3 - t2)

        combined_worst_case_times.append((t1 - t0) + (t3 - t2))

    def stats(values: list[float]) -> dict:
        arr = np.array(values) * 1000.0
        return {"mean_ms": float(arr.mean()), "p95_ms": float(np.percentile(arr, 95)), "max_ms": float(arr.max())}

    window_stats = stats(window_extraction_times)
    ml_stats = stats(ml_inference_times)
    combined_stats = stats(combined_worst_case_times)

    demo_tick_interval_s = window_seconds * (1 - settings.audio_window_overlap)  # at playback_speed=1.0
    demo_tick_interval_ms = demo_tick_interval_s * 1000.0
    effective_windows_per_second = 1.0 / (window_stats["mean_ms"] / 1000.0)

    print(f"Benchmarked {len(files)} real bearing WAV files")
    print(f"Deterministic feature extraction (per 1s window, band_type={settings.octave_mode}): {window_stats}")
    print(f"ML inference (per WHOLE 10s clip, once per file play): {ml_stats}")
    print(f"Combined worst-case (window + ML co-occurring in the same tick): {combined_stats}")
    print(f"Demo per-window tick budget at playback_speed=1.0: {demo_tick_interval_ms:.1f} ms")
    print(f"Effective deterministic processing rate: {effective_windows_per_second:.1f} windows/sec")
    print(
        f"ML fits within one tick budget: "
        f"{combined_stats['p95_ms'] < demo_tick_interval_ms} "
        f"({combined_stats['p95_ms']:.1f}ms p95 vs {demo_tick_interval_ms:.1f}ms budget)"
    )

    result = {
        "n_files": len(files),
        "window_seconds": window_seconds,
        "clip_duration_seconds": 10.0,
        "model_available": model.available,
        "deterministic_window_extraction_ms": window_stats,
        "ml_inference_per_clip_ms": ml_stats,
        "combined_worst_case_ms": combined_stats,
        "demo_tick_budget_ms_at_speed_1x": demo_tick_interval_ms,
        "effective_deterministic_windows_per_second": effective_windows_per_second,
        "ml_fits_within_tick_budget_p95": bool(combined_stats["p95_ms"] < demo_tick_interval_ms),
        "note": "ML inference runs ONCE per clip play/loop-around, not once per window (this model's "
        "true unit of analysis is the whole clip) - the 'combined worst case' models the rare tick "
        "where a file reopen coincides with a window-processing step, to confirm even that doesn't "
        "stall the asyncio loop. Measured directly, not extrapolated from thermal/vibration ML.",
    }
    import json

    out_path = REPO_ROOT / "models" / "acoustic" / "runtime_benchmark.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
