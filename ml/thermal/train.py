#!/usr/bin/env python
"""Trains the Multimodal Machine Health Monitoring and Anomaly Detection thermal classifier (Dataset 1, 6 classes) via
transfer learning from MobileNetV3-Small.

Reproducible: fixed seed, deterministic dataloader shuffling. Does not
touch the test split at all during training - only train/validation.
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader
from torchvision import transforms

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.thermal.dataset import CLASS_MEANING, ThermalManifestDataset, class_names_from_manifest, compute_class_weights, load_manifest_records  # noqa: E402
from ml.thermal.model import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD, build_model, count_trainable_parameters, save_checkpoint  # noqa: E402

SEED = 42
BATCH_SIZE = 16
MAX_EPOCHS = 30
EARLY_STOP_PATIENCE = 5
LEARNING_RATE = 3e-4
WEIGHT_DECAY = 1e-4

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "models" / "thermal"
CHECKPOINT_PATH = MODEL_DIR / "thermal_mobilenetv3_small_v1.pt"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def build_transforms():
    train_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.RandomHorizontalFlip(p=0.5),
            # Mild geometric jitter only - no color/hue/grayscale augmentation,
            # since the thermal palette itself carries the signal.
            transforms.RandomAffine(degrees=10, translate=(0.05, 0.05), scale=(0.95, 1.05)),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    return train_transform, eval_transform


@torch.no_grad()
def evaluate_split(model: nn.Module, loader: DataLoader, device: str) -> tuple[float, float]:
    model.eval()
    all_preds, all_labels = [], []
    total_loss = 0.0
    criterion = nn.CrossEntropyLoss()
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)
        total_loss += loss.item() * images.size(0)
        preds = logits.argmax(dim=1)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())
    avg_loss = total_loss / len(loader.dataset)
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return avg_loss, macro_f1


def main() -> None:
    set_seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    records = load_manifest_records()
    class_names = class_names_from_manifest(records)
    print(f"Classes ({len(class_names)}): {class_names}")

    train_transform, eval_transform = build_transforms()
    train_ds = ThermalManifestDataset("train", class_names, transform=train_transform)
    val_ds = ThermalManifestDataset("validation", class_names, transform=eval_transform)

    print("Train class counts:", dict(train_ds.class_counts()))
    print("Validation class counts:", dict(val_ds.class_counts()))

    generator = torch.Generator().manual_seed(SEED)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, generator=generator, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    model = build_model(num_classes=len(class_names), freeze_backbone=True).to(device)
    trainable, total = count_trainable_parameters(model)
    print(f"Trainable parameters: {trainable:,} / {total:,} ({100*trainable/total:.1f}%)")

    class_weights = compute_class_weights(train_ds).to(device)
    print("Class weights (inverse frequency):", {n: round(w, 3) for n, w in zip(class_names, class_weights.tolist())})
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)

    best_val_f1 = -1.0
    epochs_without_improvement = 0
    history = []

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)

        train_loss = running_loss / len(train_loader.dataset)
        val_loss, val_f1 = evaluate_split(model, val_loader, device)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss, "val_macro_f1": val_f1})
        print(f"Epoch {epoch:2d}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} val_macro_f1={val_f1:.4f}")

        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            epochs_without_improvement = 0
            save_checkpoint(model, CHECKPOINT_PATH)
            print(f"  -> new best (val_macro_f1={val_f1:.4f}), checkpoint saved")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= EARLY_STOP_PATIENCE:
                print(f"Early stopping at epoch {epoch} (no improvement for {EARLY_STOP_PATIENCE} epochs)")
                break

    print(f"\nBest validation macro-F1: {best_val_f1:.4f}")
    print(f"Best checkpoint: {CHECKPOINT_PATH}")
    return {
        "class_names": class_names,
        "best_val_macro_f1": best_val_f1,
        "history": history,
        "checkpoint_path": str(CHECKPOINT_PATH),
        "train_count": len(train_ds),
        "validation_count": len(val_ds),
    }


if __name__ == "__main__":
    start = time.time()
    result = main()
    print(f"\nTraining wall time: {time.time()-start:.1f}s")
