"""Central configuration for IDEA LAB.

All processing parameters live here (or are overridable via environment
variables / a .env file) so no module hardcodes tunable constants.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDEALAB_", env_file=".env", extra="ignore")

    # --- General ---
    app_name: str = "IDEA LAB"
    environment: str = "development"

    # --- Paths ---
    repo_root: Path = REPO_ROOT
    data_dir: Path = REPO_ROOT / "data"
    dataset_dir: Path = REPO_ROOT / "DATASET"
    video_dir: Path = REPO_ROOT / "VIDEO"
    manifest_dir: Path = REPO_ROOT / "data" / "manifests"
    models_dir: Path = REPO_ROOT / "models"
    db_path: Path = REPO_ROOT / "backend" / "idealab.db"
    log_dir: Path = REPO_ROOT / "backend" / "logs"

    # --- Thermal processing ---
    thermal_processing_fps: float = 5.0
    thermal_hotspot_percentile: float = 99.0
    # ML inference runs every Nth deterministically-processed thermal frame,
    # not every frame. Measured on a real 1920x1080 demo clip: ML inference
    # costs ~58ms/frame on this CPU, and the deterministic analyzer alone
    # already uses most of the 200ms budget for the 5fps target above -
    # running ML every frame leaves only ~31% headroom over that target.
    # stride=2 (2.5 ML inferences/sec, within the suggested 2-5/sec range)
    # measured at ~43% headroom (7.15 effective FPS vs the 5.0 target).
    thermal_ml_inference_stride: int = 2
    thermal_ml_confidence_threshold: float = 0.6

    # --- Vibration processing ---
    vibration_window_seconds: float = 1.0
    vibration_window_overlap: float = 0.5
    vibration_default_sample_rate: int = 20000
    # RF inference on a 10-feature vector is cheap (see benchmark in
    # scripts/benchmark_vibration_ml.py) - unlike thermal ML, no stride is
    # needed; ML runs on every processed window.
    vibration_ml_confidence_threshold: float = 0.90

    # --- Acoustic processing ---
    audio_window_seconds: float = 1.0
    audio_window_overlap: float = 0.5
    audio_default_sample_rate: int = 16000
    fft_size: int = 2048
    stft_hop: int = 512
    mfcc_n_coeffs: int = 13
    octave_mode: str = "octave"  # "octave" | "third_octave"
    # Acoustic ML V1 was trained on whole-10-second-clip features (both
    # octave AND third-octave bands), not the analyzer's short streaming
    # windows - see app.pipelines.acoustic.ml_model's docstring. Inference
    # therefore runs once per demo clip play/loop-around, not per window.
    acoustic_ml_confidence_threshold: float = 0.80

    # --- Baseline / anomaly ---
    baseline_min_observations: int = 180
    anomaly_z_threshold: float = 3.0

    # --- Temporal fusion / health smoothing ---
    health_smoothing_alpha: float = 0.3  # EWMA weight for latest observation
    anomaly_persistence_frames: int = 5  # consecutive abnormal frames before raising an event
    anomaly_clear_frames: int = 8  # consecutive normal frames before clearing an event (hysteresis)

    # --- Demo mode ---
    demo_playback_speed: float = 1.0

    # --- API / realtime ---
    # The production process binds via the Render-provided $PORT through the
    # start command itself (uvicorn app.main:app --host 0.0.0.0 --port
    # $PORT) - api_host/api_port below are only used by local dev scripts
    # that launch uvicorn programmatically, never by Render.
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Deployed frontend origins are added via IDEALAB_CORS_ORIGINS - a
    # plain comma-separated string, since Render's env var UI (and most
    # host dashboards) can't cleanly enter a JSON array. Kept as `str`
    # rather than `list[str]` deliberately: pydantic-settings tries to
    # JSON-decode env values for list-typed fields before any validator
    # runs, which hard-fails on a plain comma-separated string. Local dev
    # origins stay in the default so nothing extra needs configuring for
    # `npm run dev`. Use `cors_origin_list` to get the parsed list.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

for _path in (settings.data_dir, settings.manifest_dir, settings.models_dir, settings.log_dir):
    _path.mkdir(parents=True, exist_ok=True)
