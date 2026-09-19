from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.schemas import DemoStartRequest, DemoStatusOut
from app.services import thermal_image_feed
from app.services.demo_runner import demo_runner
from app.services.demo_scenarios import list_machine_videos, list_scenarios

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/scenarios")
def get_demo_scenarios() -> list[dict]:
    """Verified, ready-to-use dataset sources for the demo UI, so the
    presenter can pick a preset instead of typing filesystem paths live."""
    return [s.model_dump() for s in list_scenarios()]


@router.get("/machine-videos")
def get_machine_videos() -> list[dict]:
    """Authoritative machine -> prerecorded thermal video registry (see
    app.services.demo_scenarios.MACHINE_VIDEOS). The frontend's machine
    selector reads this list instead of accepting a typed machine name or
    a raw video path - Video 6 is intentionally absent, by construction."""
    return [entry.model_dump() for entry in list_machine_videos()]


@router.post("/start", response_model=DemoStatusOut)
async def start_demo(payload: DemoStartRequest) -> DemoStatusOut:
    if demo_runner.is_running:
        raise HTTPException(status_code=409, detail="A demo session is already running")
    return await demo_runner.start(payload)


@router.post("/stop", response_model=DemoStatusOut)
async def stop_demo() -> DemoStatusOut:
    return await demo_runner.stop()


@router.get("/status", response_model=DemoStatusOut)
def demo_status() -> DemoStatusOut:
    return demo_runner.status()


@router.get("/thermal-video")
def get_thermal_video() -> FileResponse:
    """Streams the CURRENTLY ACTIVE demo session's thermal source file for
    the dashboard's visible <video> element - a visual convenience only.

    This never introduces a new file-traversal surface: the path served is
    exactly the one the operator already supplied to POST /demo/start
    (validated the same way ThermalVideoReader already trusts it - this is
    a local, single-operator demo tool, not a multi-tenant service), never
    a client-supplied path in THIS request. The backend's own thermal
    processing (frame reading, deterministic analysis, ML inference,
    confidence gating) is completely independent of this endpoint - it
    reads the same file separately via ThermalVideoReader and never waits
    on or depends on browser playback.

    FileResponse streams from disk (never loads the whole file into
    memory) and Starlette handles HTTP Range requests automatically, so
    browser seeking/scrubbing works.
    """
    status = demo_runner.status()
    source = status.sources.get("thermal") if status.sources else None
    if not status.running or not source:
        raise HTTPException(status_code=404, detail="No active thermal demo source")

    path = Path(source)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Thermal source file not found: {source}")

    # No `filename=` - that would default Content-Disposition to
    # "attachment" and make the browser download instead of play inline.
    return FileResponse(path, media_type="video/mp4")


@router.get("/thermal-image-feed")
def get_thermal_image_feed() -> list[dict]:
    """A small, fixed, curated set of real Thermal V1 TEST-split images
    with the existing model's confidence-gated prediction already
    computed (once, cached) - the frontend cycles through this list
    locally, one image per second. Not part of the live demo_runner
    pipeline; does not require a running demo session."""
    return thermal_image_feed.build_feed()


@router.get("/thermal-image-feed/{image_id}")
def get_thermal_feed_image(image_id: str) -> FileResponse:
    path = thermal_image_feed.get_image_path(image_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown thermal feed image: {image_id}")
    return FileResponse(path, media_type="image/jpeg")
