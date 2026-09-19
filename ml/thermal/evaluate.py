#!/usr/bin/env python
"""Evaluates the trained thermal classifier on the UNTOUCHED test split.

Run only after train.py has produced a checkpoint. This script does not
train anything and is not used to pick the model - it exists purely to
report honest test-set performance.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    top_k_accuracy_score,
)
from torch.utils.data import DataLoader
from torchvision import transforms

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.thermal.dataset import ThermalManifestDataset, class_names_from_manifest, load_manifest_records  # noqa: E402
from ml.thermal.model import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD, build_model, load_checkpoint  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_PATH = REPO_ROOT / "models" / "thermal" / "thermal_mobilenetv3_small_v1.pt"


@torch.no_grad()
def run_inference(model, loader, device) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model.eval()
    all_probs, all_labels, all_paths = [], [], []
    for images, labels in loader:
        images = images.to(device)
        logits = model(images)
        probs = torch.softmax(logits, dim=1)
        all_probs.append(probs.cpu().numpy())
        all_labels.extend(labels.tolist())
    return np.concatenate(all_probs), np.array(all_labels)


def main() -> dict:
    device = "cpu"
    records = load_manifest_records()
    class_names = class_names_from_manifest(records)

    eval_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    test_ds = ThermalManifestDataset("test", class_names, transform=eval_transform)
    test_loader = DataLoader(test_ds, batch_size=16, shuffle=False, num_workers=0)
    print(f"Test set: {len(test_ds)} images. Class counts: {dict(test_ds.class_counts())}")

    model = build_model(num_classes=len(class_names), freeze_backbone=True).to(device)
    load_checkpoint(model, CHECKPOINT_PATH)

    start = time.time()
    probs, labels = run_inference(model, test_loader, device)
    elapsed = time.time() - start
    preds = probs.argmax(axis=1)

    accuracy = float((preds == labels).mean())
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, preds, average=None, labels=list(range(len(class_names))), zero_division=0
    )
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        labels, preds, average="macro", zero_division=0
    )
    cm = confusion_matrix(labels, preds, labels=list(range(len(class_names))))

    top1 = float(top_k_accuracy_score(labels, probs, k=1, labels=list(range(len(class_names)))))
    top3 = float(top_k_accuracy_score(labels, probs, k=3, labels=list(range(len(class_names)))))

    print(f"\nTest inference wall time: {elapsed:.3f}s for {len(test_ds)} images "
          f"({elapsed/len(test_ds)*1000:.1f} ms/image average)")
    print(f"\nAccuracy: {accuracy:.4f}")
    print(f"Macro precision: {macro_precision:.4f}")
    print(f"Macro recall: {macro_recall:.4f}")
    print(f"Macro F1: {macro_f1:.4f}")
    print(f"Top-1 accuracy: {top1:.4f}")
    print(f"Top-3 accuracy: {top3:.4f}")

    print("\nPer-class metrics:")
    print(f"{'class':8s} {'precision':>10s} {'recall':>10s} {'f1':>8s} {'support':>8s}")
    for i, name in enumerate(class_names):
        print(f"{name:8s} {precision[i]:10.3f} {recall[i]:10.3f} {f1[i]:8.3f} {support[i]:8d}")

    print("\nConfusion matrix (rows=true, cols=predicted):")
    print("        " + " ".join(f"{n:>6s}" for n in class_names))
    for i, name in enumerate(class_names):
        print(f"{name:8s}" + " ".join(f"{cm[i][j]:6d}" for j in range(len(class_names))))

    # error analysis: list misclassified test images
    misclassified = []
    for idx, (path, true_label) in enumerate(test_ds.samples):
        if preds[idx] != true_label:
            misclassified.append(
                {
                    "image_path": path,
                    "true_class": class_names[true_label],
                    "predicted_class": class_names[preds[idx]],
                    "confidence": float(probs[idx][preds[idx]]),
                }
            )
    print(f"\nMisclassified: {len(misclassified)} / {len(test_ds)}")
    for m in misclassified:
        print(f"  {Path(m['image_path']).name}: true={m['true_class']} pred={m['predicted_class']} conf={m['confidence']:.3f}")

    return {
        "class_names": class_names,
        "accuracy": accuracy,
        "macro_precision": float(macro_precision),
        "macro_recall": float(macro_recall),
        "macro_f1": float(macro_f1),
        "top1_accuracy": top1,
        "top3_accuracy": top3,
        "confusion_matrix": cm.tolist(),
        "per_class": {
            name: {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]), "support": int(support[i])}
            for i, name in enumerate(class_names)
        },
        "misclassified": misclassified,
        "test_count": len(test_ds),
        "avg_inference_seconds": elapsed / len(test_ds),
    }


if __name__ == "__main__":
    result = main()
    out_path = Path(__file__).resolve().parents[2] / "models" / "thermal" / "test_evaluation.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nFull results written to {out_path}")
