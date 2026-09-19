"""Evidence/score-level multimodal fusion.

Deliberately NOT raw signal concatenation - each modality is analyzed
independently (thermal/vibration/acoustic pipelines + per-modality anomaly
detection), and only the resulting AnomalyResult evidence is fused here.
This matches the project's fusion principle: the available datasets are not
guaranteed to be synchronized recordings of the same physical machine, so
fusing raw signals would be meaningless.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.anomaly.detector import AnomalyResult
from app.models.schemas import EvidenceItem, MachineHealthState, Modality

ALL_MODALITIES: list[Modality] = ["thermal", "vibration", "acoustic"]


class ModalitySnapshot(BaseModel):
    """One modality's anomaly result for the current fusion cycle, plus the
    raw feature values needed to populate evidence line items."""

    modality: Modality
    anomaly: AnomalyResult
    raw_features: dict[str, float] = {}


class FusionEngine:
    def __init__(
        self,
        severity_z_cap: float = 10.0,
        critical_z_threshold: float = 6.0,
        max_evidence_per_modality: int = 5,
    ) -> None:
        self._severity_z_cap = severity_z_cap
        self._critical_z_threshold = critical_z_threshold
        self._max_evidence_per_modality = max_evidence_per_modality

    def combine(
        self,
        machine_id: str,
        timestamp: datetime,
        snapshots: list[ModalitySnapshot],
        model_version: str | None = None,
    ) -> MachineHealthState:
        present_modalities = {s.modality for s in snapshots}
        missing_modalities = [m for m in ALL_MODALITIES if m not in present_modalities]

        calibrated = [s for s in snapshots if s.anomaly.status != "unknown"]

        if not calibrated:
            return MachineHealthState(
                machine_id=machine_id,
                timestamp=timestamp,
                status="unknown",
                confidence=0.0,
                missing_modalities=missing_modalities,
                evidence=[
                    EvidenceItem(modality=s.modality, feature="baseline", note=s.anomaly.reason)
                    for s in snapshots
                    if s.anomaly.reason
                ],
            )

        modality_contributions: dict[str, float] = {}
        evidence: list[EvidenceItem] = []
        severities: list[float] = []

        for s in calibrated:
            zscores = s.anomaly.statistical_zscores
            contributing = s.anomaly.statistical_contributing_features
            max_abs_z = max((abs(zscores[f]) for f in contributing), default=0.0)

            # An Isolation Forest flag with no single feature over threshold
            # still indicates a real (joint-feature) anomaly - make sure it
            # registers as at least a mild severity bump rather than being lost.
            if s.anomaly.isolation_forest_status == "anomalous":
                max_abs_z = max(max_abs_z, self._critical_z_threshold / 2)

            severity = min(max_abs_z / self._severity_z_cap, 1.0)
            severities.append(severity)
            modality_contributions[s.modality] = round(severity, 3)

            for feature in contributing[: self._max_evidence_per_modality]:
                evidence.append(
                    EvidenceItem(
                        modality=s.modality,
                        feature=feature,
                        value=s.raw_features.get(feature),
                        deviation=zscores.get(feature),
                    )
                )
            if s.anomaly.isolation_forest_status == "anomalous" and not contributing:
                evidence.append(
                    EvidenceItem(
                        modality=s.modality,
                        feature="isolation_forest",
                        note=f"Flagged as an outlier by Isolation Forest (score={s.anomaly.isolation_forest_score:.3f})",
                    )
                )

        avg_severity = sum(severities) / len(severities)
        health_score = round(100 * (1 - avg_severity), 1)

        anomalous_modalities = [s.modality for s in calibrated if s.anomaly.status == "anomalous"]
        if len(anomalous_modalities) >= 2 or avg_severity >= (self._critical_z_threshold / self._severity_z_cap):
            status, severity_label = "critical", "high"
        elif anomalous_modalities:
            status, severity_label = "warning", "moderate"
        else:
            status, severity_label = "normal", None

        confidence = round(len(calibrated) / len(ALL_MODALITIES), 2)

        return MachineHealthState(
            machine_id=machine_id,
            timestamp=timestamp,
            health_score=health_score,
            status=status,
            severity=severity_label,
            confidence=confidence,
            modality_contributions=modality_contributions,
            missing_modalities=missing_modalities,
            evidence=evidence,
            model_version=model_version,
        )
