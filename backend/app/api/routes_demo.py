from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import json

from app.core.config import settings
from app.core.paths import REPO_ROOT
from app.models.schemas import DemoStartRequest, DemoStatusOut
from app.pipelines.acoustic.readers import AudioFileReader
from app.pipelines.thermal.readers import ThermalVideoReader
from app.pipelines.vibration.readers import IMSVibrationDatasetReader
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


def _validate_sources(payload: DemoStartRequest) -> None:
    """Open each requested source with the same reader the replay will use, so a source
    that could never be replayed is rejected here instead of starting a silent, empty loop."""
    if not (payload.thermal_source or payload.vibration_source or payload.acoustic_source):
        raise HTTPException(status_code=400, detail="Provide at least one source to replay.")

    def reject(label: str, exc: Exception) -> HTTPException:
        # A missing file is reported without the server's filesystem path (this API may be reachable from outside).
        reason = "the file is not available on this server" if isinstance(exc, FileNotFoundError) else str(exc)
        return HTTPException(status_code=422, detail=f"{label} source cannot be replayed: {reason}")

    if payload.thermal_source:
        reader = ThermalVideoReader(payload.thermal_source)
        try:
            reader.open()
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise reject("Thermal video", exc) from exc
        finally:
            reader.close()
    if payload.acoustic_source:
        audio = AudioFileReader(payload.acoustic_source)
        try:
            audio.open()
        except (FileNotFoundError, OSError, ValueError, EOFError) as exc:
            raise reject("Sound", exc) from exc
        finally:
            audio.close()
    if payload.vibration_source:
        vibration = IMSVibrationDatasetReader(
            Path(payload.vibration_source),
            channel=payload.vibration_channel,
            sample_rate=settings.vibration_default_sample_rate,
            start_file=payload.vibration_start_file,
            end_file=payload.vibration_end_file,
        )
        try:
            vibration.open()
            vibration.read_chunk(1)  # loads the first file, which also checks the channel exists
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise reject("Vibration", exc) from exc
        finally:
            vibration.close()


@router.post("/start", response_model=DemoStatusOut)
async def start_demo(payload: DemoStartRequest) -> DemoStatusOut:
    if demo_runner.is_running:
        raise HTTPException(status_code=409, detail="A demo session is already running")
    _validate_sources(payload)
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
    # Only catalogued project videos are ever served, whatever source a session was started with.
    catalogued = {Path(v.path).resolve() for v in list_machine_videos()} | {
        Path(s.source).resolve() for s in list_scenarios() if s.modality == "thermal"
    }
    if path.resolve() not in catalogued:
        raise HTTPException(status_code=403, detail="The active thermal source is not a catalogued demo video")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Thermal source file not found: {source}")
    if settings.video_preview_dir is not None:  # lighter copy of the SAME catalogued video, for the browser player only
        preview = settings.video_preview_dir / path.name
        if preview.is_file():
            path = preview

    # No `filename=` - that would default Content-Disposition to
    # "attachment" and make the browser download instead of play inline.
    return FileResponse(path, media_type="video/mp4")


@router.get("/thermal-evaluation")
def get_thermal_evaluation() -> dict:
    """Saved held-out TEST-image results of the thermal classifier, read from its evaluation artifact.
    These are image results; accuracy on the demo videos has not been measured."""
    model_dir = REPO_ROOT / "models" / "thermal"
    try:
        evaluation = json.loads((model_dir / "test_evaluation.json").read_text(encoding="utf-8"))
        metadata = json.loads((model_dir / "model_metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Thermal evaluation artifact unavailable: {exc}") from exc
    keys = ("accuracy", "macro_precision", "macro_recall", "macro_f1", "top1_accuracy", "top3_accuracy",
            "test_count", "class_names", "per_class", "avg_inference_seconds")
    return {"model_version": metadata.get("model_version"), "dataset": metadata.get("dataset"),
            **{k: evaluation.get(k) for k in keys}}


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
