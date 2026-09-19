"""Verified demo scenarios: known-good dataset sources/ranges for the
presenter to pick from instead of typing raw filesystem paths live.

Every path is resolved relative to `settings.dataset_dir`/`video_dir`
(never a machine-specific absolute path baked in), and every IMS file
range below was determined by actually inspecting the real data - not
guessed - documented inline. See docs/DEVELOPMENT.md for the full
investigation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.config import settings


class DemoScenario(BaseModel):
    scenario_id: str
    label: str
    modality: Literal["thermal", "vibration", "acoustic"]
    source: str  # absolute path, resolved at registry-build time
    channel: int | None = None
    start_file: int | None = None
    end_file: int | None = None
    notes: str


def _thermal_path(name: str) -> str:
    return str(settings.video_dir / name)


def _dataset_path(*parts: str) -> str:
    return str(settings.dataset_dir.joinpath(*parts))


DEMO_SCENARIOS: dict[str, DemoScenario] = {
    "thermal_engine_warmup": DemoScenario(
        scenario_id="thermal_engine_warmup",
        label="Thermal — Engine Warm-Up",
        modality="thermal",
        # VIDEO/ files were renamed to 1.mp4..8.mp4 outside this codebase at some
        # point after this scenario was created; "1.mp4" was confirmed (via a
        # visual frame check - "SUBARU CROSSTREK" watermark visible) to still be
        # this same engine warm-up footage, just re-encoded (fps 29.97 -> 24).
        source=_thermal_path("1.mp4"),
        notes="Shows a real, visible heat build-up over time - the only thermal clip with a clean narrative arc.",
    ),
    "ims_bearing_healthy": DemoScenario(
        scenario_id="ims_bearing_healthy",
        label="IMS Bearing — Healthy",
        modality="vibration",
        source=_dataset_path("IMS", "IMS", "1st_test", "1st_test"),
        channel=4,
        start_file=0,
        end_file=140,
        notes=(
            "Bounded to the confirmed-stable early region of the real IMS 1st_test bearing-3 "
            "run-to-failure sequence. Verified by direct inspection: RMS is flat (~0.129-0.133) "
            "through file 154, then step-jumps to ~0.16 at file 156 - end_file=140 leaves a safety "
            "margin before that jump so this scenario stays healthy indefinitely (it loops within "
            "[0, 140])."
        ),
    ),
    "ims_bearing_degraded": DemoScenario(
        scenario_id="ims_bearing_degraded",
        label="IMS Bearing — Degraded",
        modality="vibration",
        source=_dataset_path("IMS", "IMS", "1st_test", "1st_test"),
        channel=4,
        start_file=0,
        end_file=2155,
        notes=(
            "The full real run-to-failure sequence (files 0-2155) for the same channel. "
            "Calibrates on the same early healthy files, then genuinely transitions through the "
            "documented step-change at file ~156 and the severe end-of-life failure (kurtosis "
            "12-18, crest factor 10-15 confirmed in files 2000-2155). This is real data, not a "
            "synthetic fault injection - use a separate machine from ims_bearing_healthy so its "
            "baseline is calibrated fresh rather than reused."
        ),
    ),
    "acoustic_bearing_normal": DemoScenario(
        scenario_id="acoustic_bearing_normal",
        label="Acoustic — Bearing (Normal)",
        modality="acoustic",
        source=_dataset_path("bearing", "bearing", "train", "section_00_source_train_normal_0000_vel_22.wav"),
        notes="A real normal-labelled training clip from the bearing acoustic dataset.",
    ),
}


def list_scenarios() -> list[DemoScenario]:
    return list(DEMO_SCENARIOS.values())


def get_scenario(scenario_id: str) -> DemoScenario | None:
    return DEMO_SCENARIOS.get(scenario_id)


class MachineVideoEntry(BaseModel):
    """One entry in the authoritative machine -> prerecorded thermal video
    registry (MACHINE_VIDEOS below). This is the SINGLE source of truth for
    which video represents which machine - the frontend's machine selector
    reads this list instead of letting a user type a machine name or a raw
    video path."""

    machine_video_id: str
    name: str
    video: str
    video_id: int
    machine_type: str
    path: str  # absolute path under settings.video_dir, resolved at import time
    notes: str


# Video 6 is a generic/unidentified clip and is DELIBERATELY excluded here -
# it must never appear in the machine list, the API, or any automatic
# rotation. Do not add it, rename it, or infer a machine for it.
MACHINE_VIDEOS: dict[str, MachineVideoEntry] = {
    "honda_engine_1": MachineVideoEntry(
        machine_video_id="honda_engine_1",
        name="Honda Engine",
        video="1.mp4",
        video_id=1,
        machine_type="engine",
        path=_thermal_path("1.mp4"),
        notes="Honda engine thermal demonstration, clip 1 of 2.",
    ),
    "honda_engine_2": MachineVideoEntry(
        machine_video_id="honda_engine_2",
        name="Honda Engine",
        video="2.mp4",
        video_id=2,
        machine_type="engine",
        path=_thermal_path("2.mp4"),
        notes="Honda engine thermal demonstration, clip 2 of 2.",
    ),
    "hydraulic": MachineVideoEntry(
        machine_video_id="hydraulic",
        name="Hydraulic System",
        video="3.mp4",
        video_id=3,
        machine_type="hydraulic",
        path=_thermal_path("3.mp4"),
        notes="Hydraulic system thermal demonstration.",
    ),
    "ev_battery": MachineVideoEntry(
        machine_video_id="ev_battery",
        name="EV Battery",
        video="4.mp4",
        video_id=4,
        machine_type="battery",
        path=_thermal_path("4.mp4"),
        notes="EV battery pack thermal demonstration.",
    ),
    "transformer": MachineVideoEntry(
        machine_video_id="transformer",
        name="Transformer",
        video="5.mp4",
        video_id=5,
        machine_type="transformer",
        path=_thermal_path("5.mp4"),
        notes="Transformer thermal demonstration.",
    ),
    "engine_with_oil": MachineVideoEntry(
        machine_video_id="engine_with_oil",
        name="Engine — With Oil",
        video="7.mp4",
        video_id=7,
        machine_type="engine",
        path=_thermal_path("7.mp4"),
        notes="Engine thermal demonstration, lubricated condition.",
    ),
    "engine_without_oil": MachineVideoEntry(
        machine_video_id="engine_without_oil",
        name="Engine — Without Oil",
        video="8.mp4",
        video_id=8,
        machine_type="engine",
        path=_thermal_path("8.mp4"),
        notes="Engine thermal demonstration, oil-starved condition.",
    ),
}


def list_machine_videos() -> list[MachineVideoEntry]:
    return sorted(MACHINE_VIDEOS.values(), key=lambda entry: entry.video_id)


def get_machine_video(machine_video_id: str) -> MachineVideoEntry | None:
    return MACHINE_VIDEOS.get(machine_video_id)
