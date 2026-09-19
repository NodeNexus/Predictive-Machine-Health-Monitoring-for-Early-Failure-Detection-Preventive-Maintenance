"""Tests for the authoritative machine -> prerecorded thermal video
registry (app.services.demo_scenarios.MACHINE_VIDEOS) and its API
exposure at GET /api/demo/machine-videos.

Video 6 is a generic/unidentified clip and must never appear anywhere in
this registry or its API surface.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.demo_scenarios import MACHINE_VIDEOS, get_machine_video, list_machine_videos

EXPECTED_MAPPING = {
    "honda_engine_1": ("Honda Engine", "1.mp4", 1, "engine"),
    "honda_engine_2": ("Honda Engine", "2.mp4", 2, "engine"),
    "hydraulic": ("Hydraulic System", "3.mp4", 3, "hydraulic"),
    "ev_battery": ("EV Battery", "4.mp4", 4, "battery"),
    "transformer": ("Transformer", "5.mp4", 5, "transformer"),
    "engine_with_oil": ("Engine — With Oil", "7.mp4", 7, "engine"),
    "engine_without_oil": ("Engine — Without Oil", "8.mp4", 8, "engine"),
}


def test_registry_has_exactly_the_seven_valid_entries():
    assert set(MACHINE_VIDEOS.keys()) == set(EXPECTED_MAPPING.keys())
    assert len(MACHINE_VIDEOS) == 7


def test_video_6_is_absent_from_the_registry():
    for entry in MACHINE_VIDEOS.values():
        assert entry.video != "6.mp4"
        assert entry.video_id != 6
    assert "video_6" not in MACHINE_VIDEOS
    assert get_machine_video("video_6") is None


def test_all_seven_video_mappings_are_correct():
    for machine_video_id, (name, video, video_id, machine_type) in EXPECTED_MAPPING.items():
        entry = get_machine_video(machine_video_id)
        assert entry is not None
        assert entry.name == name
        assert entry.video == video
        assert entry.video_id == video_id
        assert entry.machine_type == machine_type
        assert entry.path == str(settings.video_dir / video)


def test_honda_engine_has_two_distinct_video_entries_same_display_name():
    honda = [entry for entry in MACHINE_VIDEOS.values() if entry.name == "Honda Engine"]
    assert len(honda) == 2
    assert {entry.video for entry in honda} == {"1.mp4", "2.mp4"}


def test_list_machine_videos_is_sorted_by_video_id():
    ids = [entry.video_id for entry in list_machine_videos()]
    assert ids == sorted(ids)
    assert 6 not in ids


def test_machine_videos_endpoint_returns_seven_entries_without_video_6():
    with TestClient(app) as client:
        resp = client.get("/api/demo/machine-videos")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 7
        assert all(item["video"] != "6.mp4" for item in payload)
        assert all(item["video_id"] != 6 for item in payload)
        names = {item["name"] for item in payload}
        assert names == {
            "Honda Engine",
            "Hydraulic System",
            "EV Battery",
            "Transformer",
            "Engine — With Oil",
            "Engine — Without Oil",
        }


def test_machine_videos_endpoint_entries_reference_real_files():
    with TestClient(app) as client:
        resp = client.get("/api/demo/machine-videos")
        for item in resp.json():
            from pathlib import Path

            assert Path(item["path"]).name == item["video"]
