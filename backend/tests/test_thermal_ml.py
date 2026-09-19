"""Tests for the thermal classifier (ml/thermal/) and its inference/evidence
utilities. Skips gracefully if the trained model or the dataset staging
folder isn't present in a given environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.thermal.dataset import class_names_from_manifest, load_manifest_records  # noqa: E402
from ml.thermal.evidence import to_health_evidence  # noqa: E402
from ml.thermal.model import build_model, count_trainable_parameters  # noqa: E402

MODEL_CHECKPOINT = REPO_ROOT / "models" / "thermal" / "thermal_mobilenetv3_small_v1.pt"
MODEL_METADATA = REPO_ROOT / "models" / "thermal" / "model_metadata.json"
DATASET1_STAGING = REPO_ROOT / "_thermal_audit_ds1"

model_available = pytest.mark.skipif(
    not (MODEL_CHECKPOINT.is_file() and MODEL_METADATA.is_file()),
    reason="Trained thermal model checkpoint not present in this environment",
)
dataset_available = pytest.mark.skipif(
    not DATASET1_STAGING.is_dir(), reason="Thermal dataset staging folder not present in this environment"
)


def test_build_model_produces_correct_output_shape():
    import torch

    model = build_model(num_classes=6)
    trainable, total = count_trainable_parameters(model)
    assert 0 < trainable < total  # backbone freezing actually did something
    x = torch.randn(2, 3, 224, 224)
    out = model(x)
    assert out.shape == (2, 6)


@dataset_available
def test_manifest_class_names_match_expected():
    records = load_manifest_records()
    classes = class_names_from_manifest(records)
    assert set(classes) == {"HFL", "HML", "HNL", "CFL", "CML", "CNL"}


def test_evidence_never_invents_severity():
    prediction = {
        "predicted_class": "CFL",
        "confidence": 0.9,
        "top_predictions": [{"class": "CFL", "confidence": 0.9}],
        "model_version": "thermal-v1",
    }
    evidence = to_health_evidence(prediction)
    assert evidence["condition_type"] == "bearing_fault_indication"
    assert evidence["operating_context"] == "full_load"
    forbidden = ("critical", "unsafe", "will fail", "moderate", "risky")
    evidence_text = str(evidence).lower()
    for word in forbidden:
        assert word not in evidence_text


def test_evidence_handles_unknown_class_honestly():
    prediction = {"predicted_class": "NOT_A_REAL_CLASS", "confidence": 0.5, "top_predictions": []}
    evidence = to_health_evidence(prediction)
    assert evidence["condition_type"] == "unknown"
    assert evidence["operating_context"] == "unknown"


@model_available
def test_thermal_classifier_loads_and_predicts_on_real_image():
    from ml.thermal.inference import ThermalClassifier

    classifier = ThermalClassifier()
    assert set(classifier.class_names) == {"HFL", "HML", "HNL", "CFL", "CML", "CNL"}

    records = load_manifest_records()
    test_images = [r["image_path"] for r in records if r["split"] == "test"]
    assert test_images, "no test images found in manifest"

    result = classifier.predict(test_images[0])
    assert result["predicted_class"] in classifier.class_names
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["top_predictions"]) == 3
    assert result["inference_seconds"] < 2.0  # generous upper bound, real average is ~20ms


@model_available
def test_thermal_classifier_missing_checkpoint_raises_clear_error(tmp_path):
    from ml.thermal.inference import ThermalClassifier

    with pytest.raises(FileNotFoundError):
        ThermalClassifier(checkpoint_path=tmp_path / "does_not_exist.pt")
