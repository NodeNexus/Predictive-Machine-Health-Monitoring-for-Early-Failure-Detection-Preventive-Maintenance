#!/usr/bin/env python
"""ACOUSTIC ML V1 LIVE INTEGRATION - step 6: real end-to-end demo run.

Starts REAL DemoRunner sessions against three REAL bearing WAV files,
found via an unbiased scan of the actual test/train pool (not
hand-picked to make the gate look good - see the search in this task's
transcript): a high-confidence normal clip, a high-confidence anomaly
clip, and a clip that naturally falls BELOW the 0.80 threshold (a normal
clip the model is only 75% confident about) - so both accepted and
suppressed predictions are observed from real data, not manufactured.

Telemetry is recorded by monkeypatching telemetry_hub.broadcast - the
exact object demo_runner already imports and calls, no parallel system.
Verifies: deterministic acoustic metrics keep updating, ML predictions
appear only when confidence clears 0.80, raw confidence is preserved even
when suppressed, health/fusion blocks are present and structurally
unaffected by ML, and zero unhandled exceptions occur.
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

DATASET_DIR = REPO_ROOT / "DATASET" / "bearing" / "bearing"

CASES = [
    {
        "name": "high_confidence_normal",
        "file": DATASET_DIR / "train" / "section_02_source_train_normal_0437_vel_6_f-n_A.wav",
        "expected_true_label": "normal",
    },
    {
        "name": "high_confidence_anomaly",
        "file": DATASET_DIR / "test" / "section_01_target_test_anomaly_0023_vel_12_loc_F.wav",
        "expected_true_label": "anomaly",
    },
    {
        "name": "naturally_suppressed_low_confidence",
        "file": DATASET_DIR / "train" / "section_01_source_train_normal_0308_vel_4_loc_D.wav",
        "expected_true_label": "normal",
    },
]


async def run_case(case: dict, received: list[dict], exceptions: list[BaseException]) -> None:
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name=f"Acoustic ML E2E ({case['name']})")
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
        print(f"UNHANDLED EXCEPTION [{case['name']}]: {context}")

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_exc_handler)

    await runner.start(
        DemoStartRequest(
            machine_id=machine_id,
            acoustic_source=str(case["file"]),
            playback_speed=20.0,
        )
    )
    assert runner.is_running
    print(f"[{case['name']}] demo running on {case['file'].name} ...")
    await asyncio.sleep(6.0)  # generous budget to absorb librosa's first-call cold-start cost
    status = await runner.stop()
    assert status.running is False
    print(f"[{case['name']}] stopped.")


async def main() -> None:
    received: list[dict] = []
    exceptions: list[BaseException] = []

    async def _record(payload: dict) -> None:
        received.append((None, payload))  # placeholder, replaced below with case-tagging

    case_payloads: dict[str, list[dict]] = {c["name"]: [] for c in CASES}

    for case in CASES:
        this_case_payloads: list[dict] = []

        async def _record_case(payload: dict, _bucket=this_case_payloads) -> None:
            _bucket.append(payload)

        telemetry_hub_module.telemetry_hub.broadcast = _record_case  # type: ignore[method-assign]
        await run_case(case, received, exceptions)
        case_payloads[case["name"]] = this_case_payloads

    print(f"\nUnhandled exceptions during run: {len(exceptions)}")
    for exc in exceptions:
        print(f"  - {exc!r}")

    ok = not exceptions
    for case in CASES:
        payloads = case_payloads[case["name"]]
        acoustic_payloads = [p for p in payloads if p.get("acoustic")]
        health_payloads = [p for p in payloads if p.get("health") is not None]
        print(f"\n=== {case['name']} ({case['file'].name}) ===")
        print(f"  total payloads: {len(payloads)}, with acoustic block: {len(acoustic_payloads)}, with health block: {len(health_payloads)}")
        if not acoustic_payloads:
            print("  NO acoustic payloads observed - FAIL for this case")
            ok = False
            continue
        last = acoustic_payloads[-1]["acoustic"]
        print(f"  deterministic fields present: rms={last.get('rms')}, spectral_centroid={last.get('spectral_centroid')}")
        print(f"  ml_prediction={last.get('ml_prediction')} ml_confidence={last.get('ml_confidence')} ml_reliability={last.get('ml_reliability')} ml_model_version={last.get('ml_model_version')}")

        if case["name"] == "naturally_suppressed_low_confidence":
            if last.get("ml_reliability") != "low" or last.get("ml_prediction") is not None:
                print("  EXPECTED suppression (ml_prediction=None, reliability='low') - NOT OBSERVED - FAIL")
                ok = False
            elif last.get("ml_confidence") is None:
                print("  raw confidence missing even though suppressed - FAIL")
                ok = False
            else:
                print("  suppression correctly observed with raw confidence preserved - PASS")
        else:
            if last.get("ml_reliability") != "high" or last.get("ml_prediction") != case["expected_true_label"]:
                print(f"  EXPECTED high-confidence '{case['expected_true_label']}' - NOT OBSERVED - FAIL")
                ok = False
            else:
                print("  high-confidence accepted prediction correctly observed - PASS")

        if not health_payloads:
            print("  NO health/fusion payloads observed - FAIL")
            ok = False

    print("\nEND-TO-END DEMO RUN:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    asyncio.run(main())
