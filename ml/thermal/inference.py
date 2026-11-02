"""Loads the trained thermal classifier and runs single-image inference.

Shared by scripts/test_thermal_model.py (CLI) and, if Multimodal Machine Health Monitoring and Anomaly Detection integration
is judged low-risk, the runtime thermal pipeline. Does not fabricate a
result if the checkpoint is missing - raises a clear error instead.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

from ml.thermal.model import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD, build_model, load_checkpoint

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = REPO_ROOT / "models" / "thermal" / "thermal_mobilenetv3_small_v1.pt"
DEFAULT_METADATA = REPO_ROOT / "models" / "thermal" / "model_metadata.json"

_INFERENCE_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ]
)


class ThermalClassifier:
    """Loads the model once; call `.predict(image_path)` repeatedly."""

    def __init__(self, checkpoint_path: Path = DEFAULT_CHECKPOINT, metadata_path: Path = DEFAULT_METADATA) -> None:
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Thermal model checkpoint not found: {checkpoint_path}")
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Thermal model metadata not found: {metadata_path}")

        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.class_names: list[str] = self.metadata["class_names"]
        self.model_version: str = self.metadata["model_version"]

        self.model = build_model(num_classes=len(self.class_names), freeze_backbone=True)
        load_checkpoint(self.model, checkpoint_path)
        self.model.eval()

    def predict(self, image_path: str | Path, top_k: int = 3) -> dict:
        image = Image.open(image_path).convert("RGB")
        tensor = _INFERENCE_TRANSFORM(image).unsqueeze(0)

        start = time.perf_counter()
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0)
        elapsed = time.perf_counter() - start

        top_indices = torch.argsort(probs, descending=True)[:top_k]
        top_predictions = [
            {"class": self.class_names[i], "confidence": float(probs[i])} for i in top_indices.tolist()
        ]

        return {
            "predicted_class": top_predictions[0]["class"],
            "confidence": top_predictions[0]["confidence"],
            "top_predictions": top_predictions,
            "inference_seconds": elapsed,
            "model_version": self.model_version,
        }
