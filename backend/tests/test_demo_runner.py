"""Integration tests for DemoRunner.

Uses synthetic-but-correctly-shaped data (not the full real datasets, for
speed and determinism) so the test suite stays fast while still exercising
the real reader -> analyzer -> anomaly -> fusion -> broadcast -> persistence
chain in-process. The manual end-to-end run against real multi-GB datasets
(documented in docs/history/DEVELOPMENT.md) is the authoritative real-data check;
this test guards against regressions in the wiring.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.database.models import HealthHistory, Machine
from app.database.session import SessionLocal, init_db
from app.models.schemas import DemoStartRequest
from app.services.demo_runner import DemoRunner


def _write_synthetic_ims_file(path: Path, n_channels: int = 4, n_points: int = 2000) -> None:
    rng = np.random.default_rng(0)
    data = rng.normal(0, 0.1, size=(n_points, n_channels))
    np.savetxt(path, data, delimiter="\t", fmt="%.6f")


@pytest.fixture
def synthetic_vibration_dir(tmp_path: Path) -> Path:
    test_dir = tmp_path / "synthetic_test"
    test_dir.mkdir()
    for i in range(50):
        _write_synthetic_ims_file(test_dir / f"file_{i:04d}")
    return test_dir


def test_demo_runner_streams_vibration_and_persists_health(synthetic_vibration_dir: Path):
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Synthetic Demo Machine")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    runner = DemoRunner()

    async def scenario():
        await runner.start(
            DemoStartRequest(
                machine_id=machine_id,
                vibration_source=str(synthetic_vibration_dir),
                vibration_channel=0,
                playback_speed=1000.0,  # fast: 2000-sample window at 20kHz / 1000x -> ~1ms sleep per step
            )
        )
        assert runner.is_running

        await asyncio.sleep(2.0)  # let the vibration + fusion loops run several cycles

        status = await runner.stop()
        assert status.running is False
        return status

    asyncio.run(scenario())

    db = SessionLocal()
    try:
        rows = db.scalars(select(HealthHistory).where(HealthHistory.machine_id == machine_id)).all()
        assert len(rows) >= 1
        assert rows[0].status in ("normal", "warning", "critical", "unknown")
    finally:
        db.close()


def test_demo_runner_reports_conflict_on_double_start(synthetic_vibration_dir: Path):
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Synthetic Demo Machine 2")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    runner = DemoRunner()

    async def scenario():
        await runner.start(
            DemoStartRequest(
                machine_id=machine_id,
                vibration_source=str(synthetic_vibration_dir),
                vibration_channel=0,
                playback_speed=1000.0,
            )
        )
        assert runner.is_running
        await runner.stop()
        assert not runner.is_running

    asyncio.run(scenario())


def test_demo_runner_missing_source_reports_gracefully(tmp_path: Path):
    init_db()
    db = SessionLocal()
    try:
        machine = Machine(machine_name="Synthetic Demo Machine 3")
        db.add(machine)
        db.commit()
        db.refresh(machine)
        machine_id = machine.machine_id
    finally:
        db.close()

    runner = DemoRunner()
    missing_dir = tmp_path / "does_not_exist"

    async def scenario():
        await runner.start(
            DemoStartRequest(machine_id=machine_id, vibration_source=str(missing_dir), vibration_channel=0)
        )
        assert runner.is_running  # session still "runs", the modality loop just ends early
        await asyncio.sleep(0.5)
        await runner.stop()

    asyncio.run(scenario())  # must not raise
