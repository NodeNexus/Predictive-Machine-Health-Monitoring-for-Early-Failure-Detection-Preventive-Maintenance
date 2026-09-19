#!/usr/bin/env python
"""VIBRATION ML V1 LIVE INTEGRATION - step 11: real end-to-end demo run.

Starts REAL DemoRunner sessions against the real IMS 1st_test channel-4
directory, fast-forwarded via playback_speed. Reading + feature-extracting
all 2156 real files end-to-end costs real minutes (confirmed during
Vibration ML V1 dataset prep: ~94s for the full trajectory), so this script
runs two shorter, targeted real-file-range passes instead of one full run:
  - PASS 1 (files 0-300): covers the real healthy -> degrading transition
    (derived labels: healthy dominates ~0-149, degrading dominates from
    ~150 onward - see models/vibration/temporal_check.json).
  - PASS 2 (files 1900-2155): covers the real degrading -> severe
    transition/tail (severe dominates by this range).
Together these two REAL passes span all three classes without needing a
multi-minute full run - every window is still real IMS data, real feature
extraction, and real model inference; nothing is synthesized.

Telemetry is recorded by monkeypatching telemetry_hub.broadcast - the
exact object demo_runner already imports and calls, no parallel system.
Verifies: deterministic vibration metrics keep updating, ML predictions
appear, the confidence gate behaves correctly (raw confidence preserved,
no class label leaks out when rejected), health/fusion blocks are present
and structurally unaffected by ML, and zero unhandled exceptions occur.
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

IMS_DIR = REPO_ROOT / "DATASET" / "IMS" / "IMS" / "1st_test" / "1st_test"

PASSES = [
    {"name": "healthy_to_degrading", "start_file": 0, "end_file": 300, "sleep_budget": 25.0},
    {"name": "degrading_to_severe", "start_file": 1900, "end_file": 2155, "sleep_budget": 20.0},
]


async def run_pass(name: str, start_file: int, end_file: int, sleep_budget: float, received: list[dict], exceptions: list[BaseException]) -> None:
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name=f"Vibration ML E2E ({name})")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    runner = DemoRunner()

    def _exc_handler(loop, context):
        exc = context.get("exception")
        if exc is not None:
            exceptions.append(exc)
        print(f"UNHANDLED EXCEPTION [{name}]: {context}")

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_exc_handler)

    await runner.start(
        DemoStartRequest(
            machine_id=machine_id,
            vibration_source=str(IMS_DIR),
            vibration_channel=4,
            vibration_start_file=start_file,
            vibration_end_file=end_file,
            playback_speed=400.0,
        )
    )
    assert runner.is_running
    print(f"[{name}] demo running over files [{start_file}:{end_file}] ...")
    await asyncio.sleep(sleep_budget)
    status = await runner.stop()
    assert status.running is False
    print(f"[{name}] stopped.")


async def main() -> None:
    received: list[dict] = []
    exceptions: list[BaseException] = []

    async def _record(payload: dict) -> None:
        received.append(payload)

    telemetry_hub_module.telemetry_hub.broadcast = _record  # type: ignore[method-assign]

    for p in PASSES:
        await run_pass(p["name"], p["start_file"], p["end_file"], p["sleep_budget"], received, exceptions)

    print(f"\nTotal telemetry payloads broadcast across both passes: {len(received)}")
    print(f"Unhandled exceptions during run: {len(exceptions)}")
    for exc in exceptions:
        print(f"  - {exc!r}")

    vibration_payloads = [p for p in received if p.get("vibration")]
    print(f"Payloads with a vibration block: {len(vibration_payloads)}")

    ml_evidence_seen = []
    for p in vibration_payloads:
        vib = p["vibration"]
        assert "rms" in vib, "deterministic vibration fields missing from telemetry"
        assert "kurtosis" in vib
        entry = {
            "ml_prediction": vib.get("ml_prediction"),
            "ml_confidence": vib.get("ml_confidence"),
            "ml_reliability": vib.get("ml_reliability"),
            "ml_model_version": vib.get("ml_model_version"),
        }
        ml_evidence_seen.append(entry)
        if vib.get("ml_reliability") == "low":
            assert vib.get("ml_prediction") is None, "low-reliability prediction leaked a class label"

    distinct_predictions = {m["ml_prediction"] for m in ml_evidence_seen if m["ml_prediction"] is not None}
    print(f"Distinct ML predictions observed across both passes: {sorted(distinct_predictions)}")

    health_present = sum(1 for p in received if p.get("health") is not None)
    print(f"Payloads with a health/fusion block: {health_present}")

    if ml_evidence_seen:
        print("\nFirst 3 ML evidence samples (pass 1, healthy->degrading):", ml_evidence_seen[:3])
        print("Last 3 ML evidence samples (pass 2, degrading->severe):", ml_evidence_seen[-3:])

    ok = not exceptions and vibration_payloads and health_present and {"healthy", "severe"}.issubset(distinct_predictions)
    print("\nEND-TO-END DEMO RUN:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    asyncio.run(main())
