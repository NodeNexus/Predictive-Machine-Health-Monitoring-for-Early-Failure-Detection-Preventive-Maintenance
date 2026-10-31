"""Does every model the demo needs actually load and run on THIS machine?  (Run with backend/.venv's python.)

It only loads real model files and runs real inference on real data. If something cannot run it says exactly what,
and exits non-zero. It never substitutes a prediction.
"""
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

print(f"python {platform.python_version()} on {platform.machine()} ({platform.system()})")
failures = []


def step(label, fn):
    start = time.perf_counter()
    try:
        result = fn()
        print(f"  OK   {label}: {result}  [{time.perf_counter() - start:.1f} s]")
        return True
    except Exception as exc:  # noqa: BLE001 - report every blocker, do not stop at the first
        print(f"  FAIL {label}: {type(exc).__name__}: {exc}")
        failures.append(label)
        return False


print("imports")
for name in ("numpy", "scipy", "sklearn", "cv2", "librosa", "soundfile", "joblib", "torch", "torchvision", "fastapi", "uvicorn"):
    step(name, lambda n=name: getattr(__import__(n), "__version__", "ok"))

print("model files present")
for rel in ("models/thermal/thermal_mobilenetv3_small_v1.pt", "models/vibration/vibration_baseline_v1.joblib",
            "models/acoustic/acoustic_baseline_v1.joblib"):
    step(rel, lambda r=rel: f"{(ROOT / r).stat().st_size / 1e6:.1f} MB")

print("models load")
from app.pipelines.acoustic.ml_model import AcousticMLModel  # noqa: E402
from app.pipelines.thermal.ml_model import ThermalMLModel  # noqa: E402
from app.pipelines.vibration.ml_model import VibrationMLModel  # noqa: E402

thermal = acoustic = None
for label, cls in (("thermal (PyTorch MobileNetV3)", ThermalMLModel), ("vibration (random forest)", VibrationMLModel),
                   ("acoustic (logistic regression)", AcousticMLModel)):
    holder = {}

    def load(c=cls, h=holder):
        h["m"] = c()
        if not h["m"].available:
            raise RuntimeError("model reports available=False (see backend log for the cause)")
        return f"{h['m'].model_version}"

    if step(label, load):
        if cls is ThermalMLModel:
            thermal = holder["m"]
        if cls is AcousticMLModel:
            acoustic = holder["m"]

print("real inference")
if thermal is not None:
    import json

    import numpy as np
    from PIL import Image

    from app.core.paths import resolve_recorded_path

    records = json.loads((ROOT / "data/manifests/thermal_dataset1_split.json").read_text(encoding="utf-8"))["records"]
    sample = next(r for r in records if r["split"] == "test")

    def thermal_predict():
        path = resolve_recorded_path(sample["image_path"])
        image = np.array(Image.open(path).convert("RGB"))
        thermal.predict(image)  # warm-up
        start = time.perf_counter()
        runs = 10
        out = [thermal.predict(image) for _ in range(runs)][-1]
        return f"known {sample['class']} -> model {out['predicted_class']}  ({(time.perf_counter() - start) / runs * 1000:.0f} ms per image)"

    step("thermal image", thermal_predict)
if acoustic is not None:
    clip = ROOT / "DATASET/bearing/bearing/train/section_00_source_train_normal_0000_vel_22.wav"
    if clip.is_file():
        step("acoustic clip", lambda: f"model {acoustic.predict(clip)['predicted_class']}")
    else:
        print("  SKIP acoustic clip: demo wav not present on this machine")

try:
    import resource  # POSIX only

    print(f"peak memory so far: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
except ImportError:
    pass

if failures:
    print(f"\nBLOCKERS: {', '.join(failures)}")
    sys.exit(1)
print("\nAll required models load and run on this machine.")
