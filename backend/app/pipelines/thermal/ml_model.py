"""Runtime wrapper around the trained thermal classifier (models/thermal/).

This is deliberately isolated from ThermalAnalyzer/ThermalEvidence: the
deterministic thermal feature pipeline (hotspot detection, mean/max/min
intensity, gradient, temporal hotspot tracking) is unchanged and remains
authoritative for anomaly/health/fusion. This module produces CONTEXTUAL
evidence only - its output never feeds baseline calibration, the anomaly
detector, fusion, or event generation.

Loads the model exactly once (import + weight load happen in __init__,
never per-frame). If torch is unavailable, the checkpoint/metadata files
are missing, or inference raises for any reason, `.available` is False (or
the failing call returns None) and the caller is expected to degrade
gracefully - never let an ML failure interrupt the deterministic thermal
loop or crash the demo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("thermal.ml_model")

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CHECKPOINT = REPO_ROOT / "models" / "thermal" / "thermal_mobilenetv3_small_v1.pt"
DEFAULT_METADATA = REPO_ROOT / "models" / "thermal" / "model_metadata.json"

# The training-side `ml.thermal` package lives at the repo root, outside
# `backend/`'s own sys.path - add it once so `import ml.thermal.model` below
# resolves regardless of what process/rootdir imported this module.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class ThermalMLModel:
    """Loads once; call `.predict(image_array)` per frame (or at a reduced rate)."""

    def __init__(self, checkpoint_path: Path = DEFAULT_CHECKPOINT, metadata_path: Path = DEFAULT_METADATA) -> None:
        self.available = False
        self.class_names: list[str] = []
        self.model_version: str | None = None
        self._model = None
        self._transform = None

        try:
            import json

            import torch
            from torchvision import transforms

            from ml.thermal.model import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD, build_model, load_checkpoint

            if not checkpoint_path.is_file():
                raise FileNotFoundError(f"Thermal ML checkpoint not found: {checkpoint_path}")
            if not metadata_path.is_file():
                raise FileNotFoundError(f"Thermal ML metadata not found: {metadata_path}")

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.class_names = metadata["class_names"]
            self.model_version = metadata["model_version"]

            model = build_model(num_classes=len(self.class_names), freeze_backbone=True)
            load_checkpoint(model, checkpoint_path)
            model.eval()

            self._model = model
            self._torch = torch
            self._transform = transforms.Compose(
                [
                    transforms.ToPILImage(),
                    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
                ]
            )
            self.available = True
            logger.info(f"Thermal ML model loaded ({self.model_version}, classes={self.class_names})")
        except Exception as exc:  # noqa: BLE001 - any failure here must not be fatal
            logger.warning(f"Thermal ML model unavailable, continuing without it: {exc}")

    def predict(self, image: np.ndarray) -> dict | None:
        """`image` is an HxWx3 RGB uint8 array (same as ThermalFrame.image).

        Returns a raw prediction dict, or None if the model isn't available
        or inference fails for any reason - never raises.
        """
        if not self.available:
            return None
        try:
            tensor = self._transform(image).unsqueeze(0)
            with self._torch.no_grad():
                logits = self._model(tensor)
                probs = self._torch.softmax(logits, dim=1).squeeze(0)
            top_indices = self._torch.argsort(probs, descending=True)[:3]
            top_predictions = [
                {"class": self.class_names[i], "confidence": float(probs[i])} for i in top_indices.tolist()
            ]
            return {
                "predicted_class": top_predictions[0]["class"],
                "confidence": top_predictions[0]["confidence"],
                "top_predictions": top_predictions,
                "model_version": self.model_version,
            }
        except Exception as exc:  # noqa: BLE001 - inference failure must not crash the caller
            logger.warning(f"Thermal ML inference failed on a frame, skipping: {exc}")
            return None
