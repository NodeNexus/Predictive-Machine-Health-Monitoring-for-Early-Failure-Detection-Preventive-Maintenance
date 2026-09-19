from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.demo_scenarios import DEMO_SCENARIOS, list_scenarios


def test_all_scenario_sources_exist_on_disk():
    for scenario in list_scenarios():
        path = Path(scenario.source)
        if scenario.modality == "vibration":
            assert path.is_dir(), f"{scenario.scenario_id}: {path} is not a directory"
        else:
            assert path.is_file(), f"{scenario.scenario_id}: {path} is not a file"


def test_ims_healthy_and_degraded_scenarios_share_calibration_region_but_differ_in_range():
    healthy = DEMO_SCENARIOS["ims_bearing_healthy"]
    degraded = DEMO_SCENARIOS["ims_bearing_degraded"]
    assert healthy.source == degraded.source
    assert healthy.channel == degraded.channel
    assert healthy.start_file == degraded.start_file == 0
    assert healthy.end_file < degraded.end_file
    # the healthy range must stay below the documented step-change (~file 156)
    assert healthy.end_file < 156


def test_scenarios_endpoint_returns_real_resolved_paths():
    with TestClient(app) as client:
        resp = client.get("/api/demo/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        ids = {s["scenario_id"] for s in scenarios}
        assert ids == {
            "thermal_engine_warmup",
            "ims_bearing_healthy",
            "ims_bearing_degraded",
            "acoustic_bearing_normal",
        }
        for s in scenarios:
            assert Path(s["source"]).exists()


def test_demo_start_request_accepts_optional_vibration_range():
    from app.models.schemas import DemoStartRequest

    req = DemoStartRequest(machine_id="m1", vibration_source="x", vibration_start_file=0, vibration_end_file=140)
    assert req.vibration_start_file == 0
    assert req.vibration_end_file == 140

    # backward compatible: omitting the new fields still works
    req2 = DemoStartRequest(machine_id="m1", vibration_source="x")
    assert req2.vibration_start_file is None
    assert req2.vibration_end_file is None
