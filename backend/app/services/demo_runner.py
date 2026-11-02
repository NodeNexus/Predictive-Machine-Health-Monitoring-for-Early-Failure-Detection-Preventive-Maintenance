"""Drives DEMO MODE: real dataset-backed input adapters feed the real
modality analyzers, real baseline/anomaly detection, and the real fusion +
temporal-smoothing engine, broadcasting real telemetry over the WebSocket
hub. Nothing here fabricates a value - every number in the telemetry
payload traces back to actual file data being decoded and analyzed.

Each modality runs its own asyncio loop at its own natural cadence (a
thermal video decodes at its own frame rate, a 20kHz vibration stream and
a 16kHz audio stream fill 1-second windows at very different wall-clock
rates); a separate fusion loop periodically combines whatever the latest
evidence from each active modality is. `playback_speed` scales how fast
each modality loop consumes its source, not the fusion broadcast cadence,
so the dashboard keeps updating at a steady rate regardless of speed.

Per-machine baselines are loaded from the DB if already calibrated;
otherwise this runner bootstraps one live from the first N observations
of the stream itself (matching the "normal operating period" baseline
workflow) - modality status stays "unknown" honestly until then.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.anomaly.baseline import BaselineEstimator, BaselineStats
from app.anomaly.detector import LayeredAnomalyDetector
from app.anomaly.isolation_forest import IsolationForestDetector
from app.anomaly.repository import load_baseline, save_baseline
from app.core.config import settings
from app.core.logging import get_logger
from app.database.models import AnomalyEvent, HealthHistory, MonitoringSession
from app.database.session import SessionLocal
from app.fusion.adapters import (
    ACOUSTIC_BASELINE_FEATURES,
    THERMAL_BASELINE_FEATURES,
    VIBRATION_BASELINE_FEATURES,
    acoustic_feature_dict,
    thermal_feature_dict,
    vibration_feature_dict,
)
from app.fusion.engine import FusionEngine, ModalitySnapshot
from app.fusion.ml_evidence import fuse_thermal_vibration_acoustic
from app.fusion.temporal import TemporalHealthTracker
from app.models.schemas import DemoStartRequest, DemoStatusOut, Modality, TelemetryPayload
from app.pipelines.acoustic.analyzer import AcousticAnalyzer
from app.pipelines.acoustic.confidence_gate import apply_confidence_gate as apply_acoustic_confidence_gate
from app.pipelines.acoustic.confidence_gate import to_telemetry_fields as acoustic_ml_telemetry_fields
from app.pipelines.acoustic.ml_model import AcousticMLModel
from app.pipelines.acoustic.readers import AudioFileReader
from app.pipelines.thermal.analyzer import ThermalAnalyzer
from app.pipelines.thermal.confidence_gate import apply_confidence_gate
from app.pipelines.thermal.ml_model import ThermalMLModel
from app.pipelines.thermal.readers import ThermalVideoReader
from app.pipelines.vibration.analyzer import VibrationAnalyzer
from app.pipelines.vibration.confidence_gate import apply_confidence_gate as apply_vibration_confidence_gate
from app.pipelines.vibration.confidence_gate import to_telemetry_fields as vibration_ml_telemetry_fields
from app.pipelines.vibration.ml_model import VibrationMLModel
from app.pipelines.vibration.readers import IMSVibrationDatasetReader
from app.services.telemetry_hub import telemetry_hub

logger = get_logger("demo_runner")

_MODEL_VERSION = "phase7-fusion-v1"
_FUSION_INTERVAL_SECONDS = 1.0


class _ModalityRuntime:
    """Live state for one modality's demo processing loop."""

    def __init__(self, modality: Modality, baseline_features: list[str], machine_id: str) -> None:
        self.modality = modality
        self.baseline_features = baseline_features
        self.machine_id = machine_id
        self.estimator = BaselineEstimator(modality=modality)
        self.stats: BaselineStats | None = None
        self.detector = LayeredAnomalyDetector(
            modality=modality,
            z_threshold=settings.anomaly_z_threshold,
            min_baseline_observations=settings.baseline_min_observations,
        )
        self.latest_features: dict[str, float] | None = None
        self.latest_rich_features: dict | None = None  # full feature model, for dashboard charts
        self.latest_ml_evidence: dict | None = None  # thermal/vibration/acoustic only - contextual, never fed into ingest()
        self.source_description: str = ""
        self.progress: dict | None = None  # real replay position reported by the file reader
        self.loop_count = 0  # times the recording has been (re)started
    def ingest(self, feature_dict: dict[str, float], rich_features=None) -> None:
        self.latest_features = feature_dict
        if rich_features is not None:
            self.latest_rich_features = rich_features.model_dump(mode="json")
        if self.stats is None:
            self.estimator.add_observation(feature_dict)
            if self.estimator.is_ready(settings.baseline_min_observations):
                self.stats = self.estimator.compute_stats()
                matrix = self.estimator.feature_matrix(self.baseline_features)
                if matrix is not None:
                    forest = IsolationForestDetector(feature_names=self.baseline_features)
                    forest.fit(matrix)
                    self.detector.set_isolation_forest(forest)
                logger.info(f"{self.modality} baseline auto-calibrated from {self.stats.observation_count} observations")
                db = SessionLocal()
                try:
                    save_baseline(db, self.machine_id, self.stats)
                finally:
                    db.close()


class DemoRunner:
    def __init__(self) -> None:
        self._session_id: str | None = None
        self._machine_id: str | None = None
        self._sources: dict[str, str | None] = {}
        self._started_at: datetime | None = None
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._runtimes: dict[Modality, _ModalityRuntime] = {}
        self._temporal = TemporalHealthTracker(
            alpha=settings.health_smoothing_alpha,
            persistence_frames=settings.anomaly_persistence_frames,
            clear_frames=settings.anomaly_clear_frames,
        )
        self._fusion = FusionEngine()

    @property
    def is_running(self) -> bool:
        return self._session_id is not None

    async def start(self, payload: DemoStartRequest) -> DemoStatusOut:
        db = SessionLocal()
        try:
            session = MonitoringSession(
                machine_id=payload.machine_id,
                mode="demo",
                source_description=(
                    f"thermal={payload.thermal_source}; "
                    f"vibration={payload.vibration_source}#ch{payload.vibration_channel}; "
                    f"acoustic={payload.acoustic_source}"
                ),
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            self._session_id = session.session_id
            self._machine_id = payload.machine_id
            self._sources = {
                "thermal": payload.thermal_source,
                "vibration": payload.vibration_source,
                "acoustic": payload.acoustic_source,
            }
            self._started_at = session.started_at
        finally:
            db.close()

        self._runtimes = {}
        self._temporal = TemporalHealthTracker(
            alpha=settings.health_smoothing_alpha,
            persistence_frames=settings.anomaly_persistence_frames,
            clear_frames=settings.anomaly_clear_frames,
        )
        self._running = True
        self._tasks = []

        speed = max(payload.playback_speed, 0.01)

        if payload.thermal_source:
            self._runtimes["thermal"] = _ModalityRuntime("thermal", THERMAL_BASELINE_FEATURES, payload.machine_id)
            self._load_or_defer_baseline("thermal", db_id=payload.machine_id)
            self._tasks.append(asyncio.create_task(self._thermal_loop(Path(payload.thermal_source), speed)))

        if payload.vibration_source:
            self._runtimes["vibration"] = _ModalityRuntime("vibration", VIBRATION_BASELINE_FEATURES, payload.machine_id)
            self._load_or_defer_baseline("vibration", db_id=payload.machine_id)
            self._tasks.append(
                asyncio.create_task(
                    self._vibration_loop(
                        Path(payload.vibration_source),
                        payload.vibration_channel,
                        speed,
                        start_file=payload.vibration_start_file,
                        end_file=payload.vibration_end_file,
                    )
                )
            )

        if payload.acoustic_source:
            self._runtimes["acoustic"] = _ModalityRuntime("acoustic", ACOUSTIC_BASELINE_FEATURES, payload.machine_id)
            self._load_or_defer_baseline("acoustic", db_id=payload.machine_id)
            self._tasks.append(asyncio.create_task(self._acoustic_loop(Path(payload.acoustic_source), speed)))

        self._tasks.append(asyncio.create_task(self._fusion_loop()))

        return self.status()

    def _load_or_defer_baseline(self, modality: Modality, db_id: str) -> None:
        db = SessionLocal()
        try:
            existing = load_baseline(db, db_id, modality)
        finally:
            db.close()
        if existing is not None:
            self._runtimes[modality].stats = existing
            logger.info(f"Loaded persisted {modality} baseline ({existing.observation_count} observations)")

    async def stop(self) -> DemoStatusOut:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []

        if self._session_id is not None:
            db = SessionLocal()
            try:
                session = db.get(MonitoringSession, self._session_id)
                if session is not None:
                    session.ended_at = datetime.now(timezone.utc)
                    db.commit()
            finally:
                db.close()

        self._session_id = None
        self._machine_id = None
        self._sources = {}
        self._started_at = None
        self._runtimes = {}
        return self.status()

    def status(self) -> DemoStatusOut:
        return DemoStatusOut(
            running=self.is_running,
            machine_id=self._machine_id,
            session_id=self._session_id,
            sources=self._sources,
            started_at=self._started_at,
        )

    # --- per-modality loops -------------------------------------------------

    async def _thermal_loop(self, path: Path, speed: float) -> None:
        analyzer = ThermalAnalyzer(hotspot_percentile=settings.thermal_hotspot_percentile)
        interval = 1.0 / settings.thermal_processing_fps / speed
        runtime = self._runtimes["thermal"]

        # Loaded exactly once for the whole demo session, never per-frame.
        # If unavailable (missing checkpoint, torch not installed, etc.),
        # ml_model.available is False and predict() always returns None -
        # the deterministic loop below is entirely unaffected either way.
        # Built in a worker thread: importing torch and loading the checkpoint takes seconds, and doing it on the
        # event loop would freeze every API call and the WebSocket (the dashboard then reports the backend as unreachable).
        ml_model = await asyncio.to_thread(ThermalMLModel)
        ml_stride = max(1, settings.thermal_ml_inference_stride)
        ml_frame_counter = 0
        while self._running:
            reader = ThermalVideoReader(path, target_fps=settings.thermal_processing_fps)
            try:
                reader.open()
            except (FileNotFoundError, OSError) as exc:
                logger.warning(f"Thermal source unavailable: {exc}")
                return
            runtime.source_description = reader.source_description
            runtime.loop_count += 1
            try:
                while self._running:
                    frame = reader.read_frame()
                    if frame is None:
                        break  # end of video - loop back and reopen for continuous demo playback
                    pos = reader.progress()
                    if pos is not None:
                        runtime.progress = {"unit": "seconds", "position": round(pos[0], 2), "total": round(pos[1], 2), "loop": runtime.loop_count}

                    # Deterministic thermal analysis - unchanged, authoritative,
                    # feeds baseline/anomaly/fusion exactly as before ML existed.
                    evidence = analyzer.process_frame(frame, reader.source_description)
                    runtime.ingest(thermal_feature_dict(evidence.features), evidence.features)

                    # ML: contextual evidence only, at a reduced rate, never
                    # touching the ingest() call above. A raised exception
                    # inside predict() is already caught internally by
                    # ThermalMLModel and returns None - this call cannot
                    # interrupt the deterministic loop.
                    if ml_frame_counter % ml_stride == 0:
                        ml_prediction = ml_model.predict(frame.image)
                        runtime.latest_ml_evidence = apply_confidence_gate(
                            ml_prediction,
                            model_version=ml_model.model_version,
                            threshold=settings.thermal_ml_confidence_threshold,
                        )
                    ml_frame_counter += 1

                    await asyncio.sleep(interval)
            finally:
                reader.close()

    async def _vibration_loop(
        self,
        test_dir: Path,
        channel: int,
        speed: float,
        start_file: int | None = None,
        end_file: int | None = None,
    ) -> None:
        analyzer = VibrationAnalyzer(
            sample_rate=settings.vibration_default_sample_rate,
            window_seconds=settings.vibration_window_seconds,
            overlap=settings.vibration_window_overlap,
            band_type=settings.octave_mode,
        )
        interval = settings.vibration_window_seconds * (1 - settings.vibration_window_overlap) / speed
        runtime = self._runtimes["vibration"]

        # Loaded exactly once for the whole demo session, never per-window.
        # If unavailable (missing model/metadata files, etc.), ml_model.
        # available is False and predict() always returns None - the
        # deterministic loop below is entirely unaffected either way.
        ml_model = await asyncio.to_thread(VibrationMLModel)

        while self._running:
            reader = IMSVibrationDatasetReader(
                test_dir,
                channel=channel,
                sample_rate=settings.vibration_default_sample_rate,
                start_file=start_file,
                end_file=end_file,
            )
            try:
                reader.open()
            except (FileNotFoundError, ValueError) as exc:
                logger.warning(f"Vibration source unavailable: {exc}")
                return
            runtime.source_description = reader.source_description
            runtime.loop_count += 1
            window_samples = int(settings.vibration_default_sample_rate * settings.vibration_window_seconds)
            try:
                while self._running:
                    chunk = reader.read_chunk(window_samples)
                    if chunk is None:
                        break
                    runtime.progress = {
                        "unit": "files",
                        "position": chunk.metadata["files_consumed"],
                        "total": chunk.metadata["total_files"],
                        "loop": runtime.loop_count,
                    }

                    # Deterministic vibration analysis - unchanged, authoritative,
                    # feeds baseline/anomaly/fusion exactly as before ML existed.
                    evidences = analyzer.process_chunk(chunk, reader.source_description)
                    for evidence in evidences:
                        runtime.ingest(vibration_feature_dict(evidence.features), evidence.features)

                        # ML: contextual evidence only, consuming the feature
                        # vector already produced above (no duplicate feature
                        # extraction), never touching the ingest() call above.
                        # A raised exception inside predict() is already
                        # caught internally by VibrationMLModel and returns
                        # None - this call cannot interrupt the deterministic
                        # loop.
                        ml_prediction = ml_model.predict(evidence.features)
                        runtime.latest_ml_evidence = apply_vibration_confidence_gate(
                            ml_prediction,
                            model_version=ml_model.model_version,
                            threshold=settings.vibration_ml_confidence_threshold,
                        )

                    await asyncio.sleep(interval)
            finally:
                reader.close()

    async def _acoustic_loop(self, path: Path, speed: float) -> None:
        analyzer = AcousticAnalyzer(
            sample_rate=settings.audio_default_sample_rate,
            window_seconds=settings.audio_window_seconds,
            overlap=settings.audio_window_overlap,
            n_mfcc=settings.mfcc_n_coeffs,
            fft_size=settings.fft_size,
            hop_length=settings.stft_hop,
            band_type=settings.octave_mode,
        )
        interval = settings.audio_window_seconds * (1 - settings.audio_window_overlap) / speed
        runtime = self._runtimes["acoustic"]

        # Loaded exactly once for the whole demo session, never per-window.
        # If unavailable (missing model/metadata files, etc.), ml_model.
        # available is False and predict() always returns None - the
        # deterministic loop below is entirely unaffected either way.
        ml_model = await asyncio.to_thread(AcousticMLModel)

        while self._running:
            reader = AudioFileReader(path)
            try:
                reader.open()
            except (FileNotFoundError, ValueError) as exc:
                logger.warning(f"Acoustic source unavailable: {exc}")
                return
            runtime.source_description = reader.source_description
            runtime.loop_count += 1

            # ML: contextual evidence only, computed ONCE per clip play
            # (this model's true unit of analysis is the whole clip - see
            # AcousticMLModel's docstring), never touching the per-window
            # ingest() calls below. A raised exception inside predict() is
            # already caught internally by AcousticMLModel and returns
            # None - this call cannot interrupt the deterministic loop.
            ml_prediction = await asyncio.to_thread(ml_model.predict, path)
            runtime.latest_ml_evidence = apply_acoustic_confidence_gate(
                ml_prediction,
                model_version=ml_model.model_version,
                threshold=settings.acoustic_ml_confidence_threshold,
            )

            window_samples = int(reader.sample_rate * settings.audio_window_seconds)
            try:
                while self._running:
                    chunk = reader.read_chunk(window_samples)
                    if chunk is None:
                        break  # end of clip - loop back and reopen so the demo stays "live"
                    pos = reader.progress()
                    if pos is not None:
                        runtime.progress = {"unit": "seconds", "position": round(pos[0], 2), "total": round(pos[1], 2), "loop": runtime.loop_count}

                    # Deterministic acoustic analysis - unchanged, authoritative,
                    # feeds baseline/anomaly/fusion exactly as before ML existed.
                    evidences = analyzer.process_chunk(chunk, reader.source_description)
                    for evidence in evidences:
                        runtime.ingest(acoustic_feature_dict(evidence.features), evidence.features)
                    await asyncio.sleep(interval)
            finally:
                reader.close()

    # --- fusion / broadcast loop ---------------------------------------------

    async def _fusion_loop(self) -> None:
        while self._running:
            await asyncio.sleep(_FUSION_INTERVAL_SECONDS)
            if not self._running or self._machine_id is None:
                continue

            snapshots: list[ModalitySnapshot] = []
            for modality, runtime in self._runtimes.items():
                if runtime.latest_features is None:
                    continue
                anomaly = runtime.detector.evaluate(runtime.latest_features, runtime.stats)
                snapshots.append(
                    ModalitySnapshot(modality=modality, anomaly=anomaly, raw_features=runtime.latest_features)
                )

            if not snapshots:
                continue

            now = datetime.now(timezone.utc)
            state = self._fusion.combine(self._machine_id, now, snapshots, model_version=_MODEL_VERSION)
            temporal = self._temporal.update(state.health_score, state.status)
            state.health_score = temporal.smoothed_health_score

            events: list[dict] = []
            if temporal.event_just_started:
                events.append({"type": "event_started", "status": state.status})
                self._record_event(state, started=True)
            if temporal.event_just_cleared:
                events.append({"type": "event_cleared"})
                self._record_event(state, started=False)

            def _telemetry_block(modality: str) -> dict | None:
                runtime = self._runtimes.get(modality)
                if runtime is None or runtime.latest_rich_features is None:
                    return None
                block = {"source": runtime.source_description, **runtime.latest_rich_features}
                # ML evidence (thermal, vibration) is additive telemetry only -
                # it is never part of runtime.latest_features (what feeds
                # baseline/anomaly/fusion above), only merged into the
                # outgoing JSON here.
                if modality == "thermal" and runtime.latest_ml_evidence is not None:
                    block.update(runtime.latest_ml_evidence)
                elif modality == "vibration" and runtime.latest_ml_evidence is not None:
                    block.update(vibration_ml_telemetry_fields(runtime.latest_ml_evidence))
                elif modality == "acoustic" and runtime.latest_ml_evidence is not None:
                    block.update(acoustic_ml_telemetry_fields(runtime.latest_ml_evidence))
                return block

            def _raw_ml_evidence(modality: str) -> dict | None:
                runtime = self._runtimes.get(modality)
                return runtime.latest_ml_evidence if runtime is not None else None

            # ML evidence fusion: pure/deterministic, consumes only the
            # already-produced per-modality ML evidence above - never
            # re-runs inference, never touches FusionEngine.combine()'s own
            # deterministic health_score/status computed above. A failure
            # here must never take down telemetry or the deterministic
            # health path, so it's isolated and logged, not raised.
            try:
                ml_fusion_result = fuse_thermal_vibration_acoustic(
                    _raw_ml_evidence("thermal"),
                    _raw_ml_evidence("vibration"),
                    _raw_ml_evidence("acoustic"),
                )
            except Exception as exc:  # noqa: BLE001 - ML fusion must never break the demo loop
                logger.warning(f"ML evidence fusion failed, continuing without it: {exc}")
                ml_fusion_result = None

            payload = TelemetryPayload(
                timestamp=now,
                machine_id=self._machine_id,
                mode="demo",
                thermal=_telemetry_block("thermal"),
                vibration=_telemetry_block("vibration"),
                acoustic=_telemetry_block("acoustic"),
                health=state,
                ml_fusion=ml_fusion_result,
                events=events,
                progress={m: r.progress for m, r in self._runtimes.items() if r.progress is not None},
            )
            await telemetry_hub.broadcast(payload.model_dump(mode="json"))
            self._persist_health(state)

    def _persist_health(self, state) -> None:
        db = SessionLocal()
        try:
            db.add(
                HealthHistory(
                    machine_id=state.machine_id,
                    session_id=self._session_id,
                    timestamp=state.timestamp,
                    health_score=state.health_score,
                    status=state.status,
                    confidence=state.confidence,
                    evidence={
                        "evidence": [e.model_dump(mode="json") for e in state.evidence],
                        "modality_contributions": state.modality_contributions,
                    },
                )
            )
            db.commit()
        finally:
            db.close()

    def _record_event(self, state, started: bool) -> None:
        db = SessionLocal()
        try:
            if started:
                db.add(
                    AnomalyEvent(
                        machine_id=state.machine_id,
                        session_id=self._session_id,
                        severity=state.severity or state.status,
                        modality_contributions=state.modality_contributions,
                        evidence={"evidence": [e.model_dump(mode="json") for e in state.evidence]},
                    )
                )
            else:
                open_event = (
                    db.query(AnomalyEvent)
                    .filter(AnomalyEvent.machine_id == state.machine_id, AnomalyEvent.resolved_at.is_(None))
                    .order_by(AnomalyEvent.started_at.desc())
                    .first()
                )
                if open_event is not None:
                    open_event.resolved_at = state.timestamp
            db.commit()
        finally:
            db.close()


demo_runner = DemoRunner()
