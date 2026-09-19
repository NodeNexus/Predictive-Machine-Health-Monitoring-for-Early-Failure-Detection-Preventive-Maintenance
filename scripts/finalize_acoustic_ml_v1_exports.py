#!/usr/bin/env python
"""ACOUSTIC ML V1 - steps 6+9 finishing touches: aggregate feature
importance by family, and write feature_schema.json + test_evaluation.json
alongside the model/metadata already saved by ml/acoustic/train.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ml.acoustic.dataset import FEATURE_COLUMNS, FEATURE_FAMILY_OF  # noqa: E402

MODEL_DIR = REPO_ROOT / "models" / "acoustic"


def main() -> None:
    metadata = json.loads((MODEL_DIR / "model_metadata.json").read_text(encoding="utf-8"))
    importance = metadata["feature_importance"]

    family_totals: dict[str, float] = {}
    family_counts: dict[str, int] = {}
    for col, value in importance.items():
        family = FEATURE_FAMILY_OF[col]
        family_totals[family] = family_totals.get(family, 0.0) + value
        family_counts[family] = family_counts.get(family, 0) + 1

    family_summary = {
        family: {
            "total_importance": total,
            "mean_importance_per_feature": total / family_counts[family],
            "n_features": family_counts[family],
        }
        for family, total in family_totals.items()
    }

    top_individual = sorted(importance.items(), key=lambda kv: -kv[1])[:10]

    metadata["feature_importance_by_family"] = family_summary
    metadata["top_10_individual_features"] = [{"feature": k, "importance": v} for k, v in top_individual]
    metadata["feature_importance_caveat"] = (
        "Importance here is mean |coefficient| magnitude from the winning logistic_regression model "
        "(features were standardized first, so magnitudes are comparable across features). This "
        "reflects which standardized features the model leans on most to separate normal/anomaly in "
        "THIS dataset's recording conditions - it is not a causal claim about which physical "
        "phenomenon drives bearing anomalies, and per the robustness_by_section_domain_group finding, "
        "the model's real-world reliability varies notably by recording section."
    )
    (MODEL_DIR / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    feature_schema = {
        "feature_order": FEATURE_COLUMNS,
        "feature_families": {
            "temporal": ["rms", "peak_amplitude", "crest_factor", "energy"],
            "spectral": [
                "dominant_frequency", "spectral_centroid", "spectral_bandwidth", "spectral_rolloff",
                "spectral_flatness", "top_spectral_peak_frequency", "top_spectral_peak_magnitude",
            ],
            "octave": [c for c in FEATURE_COLUMNS if c.startswith("octave_band_")],
            "third_octave": [c for c in FEATURE_COLUMNS if c.startswith("third_octave_band_")],
            "mfcc": [c for c in FEATURE_COLUMNS if c.startswith("mfcc_")],
        },
        "feature_source": "app.pipelines.acoustic.features.extract_acoustic_features (the existing, "
        "already-validated acoustic pipeline), called twice per clip (band_type='octave' and "
        "band_type='third_octave') to get both band representations - no new feature-extraction "
        "implementation was introduced.",
        "input_unit_of_analysis": "One whole 10-second WAV clip (160,000 samples at 16kHz) = one "
        "feature vector, matching the dataset's own per-clip label granularity. No sub-windowing.",
        "preprocessing": "StandardScaler fit on train only, applied to the exported logistic_regression "
        "model (features are standardized so coefficient-magnitude importance is comparable).",
    }
    (MODEL_DIR / "feature_schema.json").write_text(json.dumps(feature_schema, indent=2), encoding="utf-8")

    test_evaluation = {
        "model_name": metadata["model_name"],
        "test_count": metadata["test_count"],
        "test_macro_f1": metadata["test_macro_f1"],
        "test_roc_auc": metadata["test_roc_auc"],
        "test_pr_auc": metadata["test_pr_auc"],
        "test_report": metadata["test_report"],
        "test_confusion_matrix": metadata["test_confusion_matrix"],
        "all_models_test_comparison": metadata["all_models_test_comparison"],
        "robustness_by_section_domain_group": metadata["robustness_by_section_domain_group"],
        "feature_importance_by_family": family_summary,
        "top_10_individual_features": metadata["top_10_individual_features"],
    }
    (MODEL_DIR / "test_evaluation.json").write_text(json.dumps(test_evaluation, indent=2), encoding="utf-8")

    print("Feature importance by family:")
    for family, summary in sorted(family_summary.items(), key=lambda kv: -kv[1]["total_importance"]):
        print(f"  {family}: total={summary['total_importance']:.3f} mean_per_feature={summary['mean_importance_per_feature']:.3f} n={summary['n_features']}")
    print("\nSaved feature_schema.json, test_evaluation.json, and updated model_metadata.json")


if __name__ == "__main__":
    main()
