"""Loads the leak-proof Dataset-1 split manifest (produced by
scripts/prepare_thermal_splits.py) as a PyTorch Dataset.

Does not copy images - reads directly from the paths recorded in the
manifest. Does not invent classes: uses exactly the 6 labels present in
the manifest (HFL/HML/HNL/CFL/CML/CNL).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "thermal_dataset1_split.json"


def resolve_image_path(recorded: str) -> Path:
    """Manifests store absolute paths from the machine that generated them. If that path is
    missing, re-root it under this checkout. Mirrors backend/app/core/paths.py (kept separate
    because ml/ does not import the backend package)."""
    path = Path(recorded)
    if path.exists():
        return path
    parts = [p for p in re.split(r"[\\/]+", recorded) if p]
    if "MECHANICAL" in parts:
        last = len(parts) - 1 - parts[::-1].index("MECHANICAL")
        if parts[last + 1 :]:
            return REPO_ROOT.joinpath(*parts[last + 1 :])
    return path

CLASS_MEANING = {
    "HFL": "Healthy / Full Load",
    "HML": "Healthy / Medium Load",
    "HNL": "Healthy / No Load",
    "CFL": "Corroded Bearing / Full Load",
    "CML": "Corroded Bearing / Medium Load",
    "CNL": "Corroded Bearing / No Load",
}


def load_manifest_records(manifest_path: Path = MANIFEST_PATH) -> list[dict]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))["records"]


def class_names_from_manifest(records: list[dict]) -> list[str]:
    return sorted({r["class"] for r in records})


class ThermalManifestDataset(Dataset):
    def __init__(
        self,
        split: str,
        class_names: list[str],
        transform=None,
        manifest_path: Path = MANIFEST_PATH,
    ) -> None:
        records = load_manifest_records(manifest_path)
        self.samples: list[tuple[str, int]] = [
            (resolve_image_path(r["image_path"]), class_names.index(r["class"])) for r in records if r["split"] == split
        ]
        if not self.samples:
            raise ValueError(f"No samples found for split={split!r} in {manifest_path}")
        self.class_names = class_names
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        image = Image.open(path).convert("RGB")
        if self.transform is not None:
            image = self.transform(image)
        return image, label

    def class_counts(self) -> Counter:
        return Counter(self.class_names[label] for _, label in self.samples)


def compute_class_weights(dataset: ThermalManifestDataset) -> torch.Tensor:
    """Inverse-frequency class weights for a weighted CrossEntropyLoss."""
    counts = dataset.class_counts()
    n_classes = len(dataset.class_names)
    total = sum(counts.values())
    weights = torch.zeros(n_classes, dtype=torch.float32)
    for i, name in enumerate(dataset.class_names):
        count = counts.get(name, 0)
        weights[i] = total / (n_classes * count) if count > 0 else 0.0
    return weights
