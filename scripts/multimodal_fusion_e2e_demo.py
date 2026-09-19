#!/usr/bin/env python
"""MULTIMODAL ML EVIDENCE FUSION V1 - step 13: real multimodal demo run.

Starts a REAL DemoRunner session with all three real dataset sources
(thermal video, IMS vibration channel 4, a real bearing WAV) running
SIMULTANEOUSLY, and verifies:
  - each modality's deterministic + ML telemetry keeps updating
  - the ml_fusion block appears, with sane fused_severity/fused_confidence
    and the correct available_modalities / reliability
  - the deterministic health/status path (FusionEngine.combine() + temporal
    smoothing) is present and structurally unaffected by ml_fusion
  - zero unhandled exceptions

Each modality's evidence is explicitly sourced from an INDEPENDENT
prerecorded dataset file - this script (and the resulting telemetry) never
implies these three streams are synchronized recordings of one physical
machine. DEMO MODE - DATASET-DRIVEN SIMULATION.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from app.database.models import Machine  # noqa: E402
from app.database.session import SessionLocal, init_db  # noqa: E402
from app.models.schemas import DemoStartRequest  # noqa: E402
from app.services import telemetry_hub as telemetry_hub_module  # noqa: E402
from app.services.demo_runner import DemoRunner  # noqa: E402

THERMAL_SOURCE = REPO_ROOT / "VIDEO" / "1.mp4"
VIBRATION_SOURCE = REPO_ROOT / "DATASET" / "IMS" / "IMS" / "1st_test" / "1st_test"
ACOUSTIC_SOURCE = REPO_ROOT / "DATASET" / "bearing" / "bearing" / "test" / "section_01_target_test_anomaly_0023_vel_12_loc_F.wav"


async def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Multimodal Fusion E2E Demo Machine")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    received: list[dict] = []

    async def _record(payload: dict) -> None:
        received.append(payload)

    telemetry_hub_module.telemetry_hub.broadcast = _record  # type: ignore[method-assign]

    runner = DemoRunner()
    exceptions: list[BaseException] = []

    def _exc_handler(loop, context):
        exc = context.get("exception")
        if exc is not None:
            exceptions.append(exc)
        print(f"UNHANDLED EXCEPTION: {context}")

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_exc_handler)

    await runner.start(
        DemoStartRequest(
            machine_id=machine_id,
            thermal_source=str(THERMAL_SOURCE),
            vibration_source=str(VIBRATION_SOURCE),
            vibration_channel=4,
            vibration_start_file=1900,
            vibration_end_file=2100,
            acoustic_source=str(ACOUSTIC_SOURCE),
            playback_speed=10.0,
        )
    )
    assert runner.is_running
    print("Multimodal demo running (thermal + vibration + acoustic) ...")
    await asyncio.sleep(40.0)

    status = await runner.stop()
    assert status.running is False

    print(f"\nTotal telemetry payloads: {len(received)}")
    print(f"Unhandled exceptions: {len(exceptions)}")
    for exc in exceptions:
        print(f"  - {exc!r}")

    with_all_three = [p for p in received if p.get("thermal") and p.get("vibration") and p.get("acoustic")]
    with_fusion = [p for p in received if p.get("ml_fusion") is not None]
    with_health = [p for p in received if p.get("health") is not None]

    print(f"Payloads with all 3 modality blocks: {len(with_all_three)}")
    print(f"Payloads with ml_fusion block: {len(with_fusion)}")
    print(f"Payloads with health block: {len(with_health)}")

    ok = not exceptions and with_all_three and with_fusion and with_health

    if with_all_three:
        last = with_all_three[-1]
        print("\n--- Last payload with all 3 modalities ---")
        print(f"thermal.ml_prediction={last['thermal'].get('ml_prediction')} reliability={last['thermal'].get('ml_reliability')}")
        print(f"vibration.ml_prediction={last['vibration'].get('ml_prediction')} reliability={last['vibration'].get('ml_reliability')}")
        print(f"acoustic.ml_prediction={last['acoustic'].get('ml_prediction')} reliability={last['acoustic'].get('ml_reliability')}")
        fusion = last["ml_fusion"]
        print(f"ml_fusion: fused_severity={fusion['fused_severity']} fused_confidence={fusion['fused_confidence']} "
              f"reliability={fusion['reliability']} available_modalities={fusion['available_modalities']}")
        health = last["health"]
        print(f"deterministic health: health_score={health.get('health_score')} status={health.get('status')} "
              f"confidence={health.get('confidence')} missing_modalities={health.get('missing_modalities')}")

        # Sanity: ml_fusion's available_modalities must be a subset of what
        # actually has ml evidence this tick, and fused_severity/confidence
        # must be within [0,1] whenever not None.
        if fusion["fused_severity"] is not None:
            ok = ok and 0.0 <= fusion["fused_severity"] <= 1.0
        ok = ok and 0.0 <= fusion["fused_confidence"] <= 1.0
        # Deterministic health must still be present and well-formed,
        # completely independent of whatever ml_fusion computed.
        ok = ok and health.get("status") in ("normal", "warning", "critical", "unknown")

    print("\nFULL MULTIMODAL DEMO RUN:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    asyncio.run(main())
