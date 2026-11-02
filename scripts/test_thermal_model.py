#!/usr/bin/env python
"""CLI: run the trained Multimodal Machine Health Monitoring and Anomaly Detection thermal classifier on a single image.

Usage:
    python scripts/test_thermal_model.py --image "<path>"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.thermal.inference import ThermalClassifier  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Multimodal Machine Health Monitoring and Anomaly Detection thermal classifier on one image.")
    parser.add_argument("--image", required=True, help="Path to a thermal JPEG image.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of top predictions to show.")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Error: image not found: {image_path}")
        raise SystemExit(1)

    classifier = ThermalClassifier()
    result = classifier.predict(image_path, top_k=args.top_k)

    print(f"Predicted class: {result['predicted_class']}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Inference time: {result['inference_seconds']*1000:.1f} ms")
    print("Top predictions:")
    for i, pred in enumerate(result["top_predictions"], start=1):
        print(f"  {i}. {pred['class']} ({pred['confidence']:.4f})")


if __name__ == "__main__":
    main()
