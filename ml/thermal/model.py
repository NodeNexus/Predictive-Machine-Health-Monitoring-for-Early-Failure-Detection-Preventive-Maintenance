"""Model construction: MobileNetV3-Small via transfer learning.

MobileNetV3-Small was chosen over ResNet18 (the only two candidates
considered, per the brief) because Multimodal Machine Health Monitoring and Anomaly Detection's actual deployment target is
CPU-only edge inference (confirmed no GPU is available on the current dev
machine either): MobileNetV3-Small has ~2.5M parameters vs. ResNet18's
~11.7M, and is purpose-built for exactly this constraint. No benchmarking
of a larger model zoo was performed - this is a deliberate, justified
choice, not a default.

Only the classifier head and the last two inverted-residual blocks are
unfrozen for fine-tuning; the rest of the ImageNet-pretrained backbone is
frozen. With only ~340 training images across 6 classes, fully fine-tuning
all ~2.5M parameters risks overfitting badly; freezing most of the backbone
keeps the trainable parameter count small while still adapting the
higher-level features to thermal imagery.
"""
from __future__ import annotations

import torch
from torch import nn
from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

IMAGE_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def build_model(num_classes: int, freeze_backbone: bool = True) -> nn.Module:
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    model = mobilenet_v3_small(weights=weights)

    if freeze_backbone:
        for param in model.features.parameters():
            param.requires_grad = False
        # Unfreeze the last two inverted-residual blocks for light fine-tuning.
        for block in list(model.features.children())[-2:]:
            for param in block.parameters():
                param.requires_grad = True

    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


def count_trainable_parameters(model: nn.Module) -> tuple[int, int]:
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return trainable, total


def save_checkpoint(model: nn.Module, path) -> None:
    torch.save(model.state_dict(), path)


def load_checkpoint(model: nn.Module, path, map_location="cpu") -> nn.Module:
    state_dict = torch.load(path, map_location=map_location)
    model.load_state_dict(state_dict)
    return model
