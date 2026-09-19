"""Fast, minimal curated Thermal V1 dataset image feed for the demo
dashboard.

This is a DISPLAY CONVENIENCE for demo time, deliberately NOT a
synchronized live pipeline: it loads a small, fixed set of real,
already-labeled Thermal V1 TEST-split images (see
data/manifests/thermal_dataset1_split.json - the same manifest
ml/thermal/dataset.py trains from), runs the EXISTING ThermalMLModel +
confidence gate on each ONCE, and caches the result for the lifetime of
the backend process. The frontend cycles through this fixed list locally
(one image per second) - no per-tick backend calls, no new inference
path, no change to the model, threshold, or confidence gate.

Uses the test split specifically (never used to train the model) so the
displayed predictions are a legitimate, unmodified evaluation of the real
Thermal ML V1 model on real, held-out images.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.pipelines.thermal.confidence_gate import apply_confidence_gate
from app.pipelines.thermal.ml_model import ThermalMLModel

logger = get_logger("thermal_image_feed")

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "thermal_dataset1_split.json"
IMAGES_PER_CLASS = 3

_feed_cache: list[dict] | None = None
_path_by_id: dict[str, Path] = {}
_model: ThermalMLModel | None = None


def _curate_records() -> list[dict]:
    all_records = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["records"]
    test_records = [r for r in all_records if r["split"] == "test"]
    by_class: dict[str, list[dict]] = {}
    for r in test_records:
        by_class.setdefault(r["class"], []).append(r)

    curated: list[dict] = []
    for class_name in sorted(by_class):  # CFL, CML, CNL, HFL, HML, HNL - deterministic order
        chosen = sorted(by_class[class_name], key=lambda r: r["image_path"])[:IMAGES_PER_CLASS]
        curated.extend(chosen)
    return curated


def build_feed() -> list[dict]:
    """Computed once per process lifetime and cached - real inference on
    ~18 images takes a moment but only ever runs once, not per request or
    per display tick."""
    global _feed_cache, _model
    if _feed_cache is not None:
        return _feed_cache

    if _model is None:
        _model = ThermalMLModel()

    records = _curate_records()
    feed: list[dict] = []
    for i, record in enumerate(records):
        image_id = f"{record['class']}_{i:02d}"
        path = Path(record["image_path"])
        _path_by_id[image_id] = path

        prediction = None
        if _model.available and path.is_file():
            try:
                from PIL import Image

                image = np.array(Image.open(path).convert("RGB"))
                prediction = _model.predict(image)
            except Exception as exc:  # noqa: BLE001 - must never break the feed
                logger.warning(f"Thermal image feed inference failed for {path}: {exc}")

        gated = apply_confidence_gate(prediction, model_version=_model.model_version)
        feed.append({"image_id": image_id, **gated})

    _feed_cache = feed
    logger.info(f"Thermal image feed built: {len(feed)} images, model_available={_model.available}")
    return feed


def get_image_path(image_id: str) -> Path | None:
    build_feed()  # ensure the id->path map is populated
    return _path_by_id.get(image_id)
