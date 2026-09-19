# Repository / Frontend Analysis

Repository: NodeNexus/Multimodal-machine-health-monitoring
Checkout inspected: G:\Hackathons\Idea Lab\repo
Commit inspected: 5469446 Update project files
Analysis date: 2026-09-16

This is a read-only architecture and frontend-readiness analysis. No application code, configuration, dependency manifest, generated runtime data, or existing contributor work was changed. The only new file is this analysis artifact.

## 1. Executive summary

IDEA LAB is a FastAPI + SQLite backend and React + TypeScript + Vite dashboard for evidence-based predictive-maintenance monitoring. It accepts three independent signal modalities—thermal imagery, vibration, and acoustic audio—and extracts modality-specific features before running per-modality baselines and anomaly detection. A fusion engine combines anomaly evidence and severity into a health state, applies EWMA smoothing and event hysteresis, persists health history/events, and broadcasts rich telemetry through a WebSocket.

The working path implemented in this checkout is dataset-backed DEMO MODE. Thermal MP4s, IMS vibration directories, and WAV files are read as streams. LIVE MODE is an architectural interface, not a complete hardware product: thermal camera discovery can probe OpenCV devices, but vibration DAQ and microphone capture backends are intentionally not integrated.

The existing frontend is a small single-page React dashboard. It already calls a substantial subset of the implemented REST routes, opens /ws/telemetry, and renders health, modality charts, history, events, devices, datasets, and demo controls. It has no router, global/query state layer, runtime payload validation, reconnect/backoff, frontend tests, or production API configuration. The most important redesign constraint is honesty: unknown, missing, disconnected, stale, uncalibrated, and non-radiometric states are real states in this system and must not be painted as healthy or as zero-valued measurements.

The backend is the source of truth for all business logic. The frontend should display backend health/status/confidence/evidence and manage interaction/connection state; it must not reimplement feature extraction, baselines, anomaly formulas, fusion, temporal smoothing, event thresholds, or thermal temperature conversion.

## 2. Product understanding

### Problem and likely users

The README describes a multimodal machine-health monitoring and predictive-maintenance platform. The code supports a maintenance/operations workflow: register a machine, select data sources, run a dataset-driven demo, inspect evidence and health history, and review anomaly events. The repository does not define authentication, roles, user accounts, or explicit personas. A future frontend can therefore use operator/maintenance/engineering language, but should not claim role-specific authorization that the backend does not provide.

### Assets/machines in scope

The domain model is generic. Machine has name, type, manufacturer, model, RPM, rated power, location, and sensor configuration. Included data covers bearings, fans, valves, gearboxes, and pumps:

- Acoustic: bearing, fan, valve, gearbox, and dev_data_pump WAV collections.
- Vibration: IMS bearing run-to-failure test sets.
- Thermal: MP4 recordings of a thermal-camera display.

The system is not limited to one machine type, but the current demo data is not guaranteed to represent synchronized measurements of the same physical asset. docs/ARCHITECTURE.md and backend/app/fusion/engine.py explicitly make fusion evidence/score-level rather than raw-signal concatenation for this reason.

### Meaning of multimodal here

The modalities are:

1. Thermal — frames converted to grayscale intensity features.
2. Vibration — streamed sample windows and time/frequency features.
3. Acoustic — streamed WAV windows and time/frequency/MFCC features.

Each modality is analyzed independently. Only the resulting anomaly/evidence snapshots are fused.

### End-to-end processing path

~~~text
thermal MP4 / thermal camera  -> thermal reader -> thermal analyzer
IMS vibration dir / DAQ      -> vibration reader -> vibration analyzer
WAV / microphone              -> acoustic reader -> acoustic analyzer
                                      |
                         per-modality baseline/anomaly layers
                                      |
                              evidence-level fusion
                                      |
                       EWMA health + event hysteresis
                                      |
                         SQLite history/event persistence
                                      |
                          WebSocket telemetry/dashboard
~~~

Relevant implementation locations:

- Input abstractions: backend/app/pipelines/common/interfaces.py
- Thermal: backend/app/pipelines/thermal/
- Vibration: backend/app/pipelines/vibration/
- Acoustic: backend/app/pipelines/acoustic/
- Baselines/anomaly detection: backend/app/anomaly/
- Fusion/temporal logic: backend/app/fusion/
- Demo lifecycle/streaming: backend/app/services/demo_runner.py
- WebSocket fan-out: backend/app/services/telemetry_hub.py
- API schemas: backend/app/models/schemas.py

### Vibration pipeline

IMSVibrationDatasetReader (backend/app/pipelines/vibration/readers.py) reads one ASCII tab-separated IMS file at a time, selects a zero-based channel, and streams samples without loading the full run. Defaults are 20 kHz sample rate, 1-second windows, and 50% overlap (backend/app/core/config.py).

VibrationAnalyzer and extract_vibration_features produce:

- Time domain: rms, variance, std, peak, peak_to_peak, crest_factor, kurtosis, skewness.
- Frequency domain: dominant_frequency, spectral_centroid, spectral_bandwidth, top-five spectral_peaks, and octave/third-octave band_energies.
- Analysis metadata: analysis_type and optional bearing_fault_frequencies (bpfo, bpfi, bsf, ftf).

Only rms, std, crest_factor, kurtosis, skewness, and spectral_centroid feed baseline/anomaly detection (backend/app/fusion/adapters.py). The complete feature model is sent in telemetry. Bearing frequencies are calculated only if RPM and bearing geometry are supplied; the current DemoRunner supplies neither, so current demo vibration is generic spectral analysis and must not be shown as a bearing-specific diagnosis.

### Acoustic pipeline

AudioFileReader (backend/app/pipelines/acoustic/readers.py) streams WAV data with the standard library wave module, supports 8/16/32-bit sample widths, downmixes multichannel input to mono, and normalizes samples approximately to [-1, 1]. AcousticAnalyzer uses 1-second windows with 50% overlap by default.

Features are:

- rms, peak_amplitude, crest_factor, energy.
- dominant_frequency, spectral_centroid, spectral_bandwidth, spectral_rolloff, spectral_flatness.
- Top-five spectral_peaks and octave/third-octave band_energies.
- 13 averaged MFCC values by default.

The baseline/anomaly adapter uses rms, crest_factor, spectral_centroid, spectral_bandwidth, spectral_flatness, and mfcc_0–mfcc_4. A full spectrogram is not in WebSocket telemetry; compute_stft() exists separately for future ML or a dedicated backend/API feature.

### Thermal pipeline

ThermalVideoReader (backend/app/pipelines/thermal/readers.py) opens an MP4, downsamples returned frames to the configured processing rate (default 5 FPS), converts BGR to RGB, and always sets is_radiometric=False. LiveThermalCamera genuinely probes an OpenCV device and raises ConnectionError if it cannot open one.

extract_thermal_features (backend/app/pipelines/thermal/features.py) converts a frame to grayscale and returns:

- mean_intensity, max_intensity, min_intensity, std_intensity.
- Percentile-derived hotspot_threshold, hotspot_pixel_count, hotspot_area_fraction.
- Nullable hotspot_centroid_x and hotspot_centroid_y (null when no hotspot pixels exist).
- gradient_mean, gradient_max, and is_radiometric.

The hotspot mask is strictly greater than the configured percentile threshold (default 99th percentile). ThermalAnalyzer also provides frame-to-frame hotspot_area_change, but the current rich telemetry block is the ThermalFeatures model and does not include that evidence-wrapper field. Only mean_intensity, max_intensity, std_intensity, hotspot_area_fraction, and gradient_mean feed the baseline/anomaly adapter.

All current thermal data is relative grayscale/brightness from visible-light recordings of a thermal display. It is not a calibrated temperature series. The frontend must never label these values as degrees Celsius unless a future backend payload actually sets is_radiometric=true and supplies calibrated semantics.

### Baseline and anomaly detection

Defaults are defined in backend/app/core/config.py:

- baseline_min_observations = 30.
- anomaly_z_threshold = 3.0.
- In-memory baseline buffer maximum: 5,000 observations (backend/app/anomaly/baseline.py).

For each machine and modality, the demo runner first attempts to load a persisted BaselineStats. If there is no usable baseline, it accumulates the first 30 feature observations, keeps the anomaly result unknown until ready, computes mean/std/p5/p95/min/max, fits an Isolation Forest when a complete training matrix is available, and saves the baseline to SQLite (backend/app/anomaly/repository.py). Machine.baseline_status becomes calibrated as soon as any modality baseline is saved; there is no public per-modality baseline status or calibration-progress endpoint.

The detector has two layers:

1. Statistical z-scores; any feature at or beyond the threshold contributes an anomaly.
2. Optional Isolation Forest; if required features are missing, it returns no score rather than assuming normal.

Either layer can make the modality anomalous. With no baseline or too few observations, the modality is unknown with a reason such as No baseline yet or Baseline has only N observation(s), needs 30. No deep-learning detector is implemented.

Persisted baseline statistics survive a restart, but the Isolation Forest training object is not persisted; a later session may therefore have statistical baseline coverage without the previous forest model.

### Multimodal fusion, health score, and confidence

FusionEngine.combine() (backend/app/fusion/engine.py) receives only modalities with a latest processed feature set. Modalities absent from the snapshot list go into missing_modalities. Unknown modalities are excluded from severity/score calculations. If no available modality is calibrated, the overall state is:

- status: unknown
- health_score: null
- confidence: 0.0
- evidence notes explaining the missing/insufficient baseline

For calibrated modalities, the implementation computes severity from the largest contributing absolute z-score, capped at 10, then computes the health score from the average calibrated severity. Confidence is calibrated modality count divided by three, not a probability of correctness. Consequently, a score of 100 can coexist with confidence 0.33 or 0.67 when only one or two modalities are calibrated. A frontend must show these together.

Current status rules:

- normal: no calibrated modality is anomalous.
- warning: one calibrated modality is anomalous.
- critical: at least two calibrated modalities are anomalous, or average severity reaches the critical threshold.
- unknown: no calibrated modality exists.

The returned state also contains optional severity (moderate for warning, high for critical), modality_contributions, missing_modalities, evidence items, and a model version when supplied by the caller (phase7-fusion-v1 in DemoRunner). The frontend must not recompute any of this.

### Temporal/history/event behavior

TemporalHealthTracker (backend/app/fusion/temporal.py) applies EWMA smoothing with default alpha 0.3. The fusion loop runs approximately once per second (_FUSION_INTERVAL_SECONDS = 1.0 in demo_runner.py). Warning/critical must persist for 5 consecutive fusion frames before a start event; an active event requires 8 consecutive normal/unknown frames before clearing. The WebSocket only emits transition entries (event_started with a status, or event_cleared); it does not continuously emit an event_active boolean.

HealthHistory persists timestamp, nullable score, status, nullable confidence, and an evidence JSON wrapper containing evidence and modality contributions. It does not persist missing modalities, severity, or model version. Therefore the status endpoint can return a complete latest state before history exists, but after history reconstruction those fields are not fully recoverable.

AnomalyEvent persists event ID, machine/session IDs, start time, nullable resolution time, severity, modality contributions, and evidence. REST history/events are newest-first.

### Missing-data behavior

- A source not configured creates no modality runtime and its telemetry block is null.
- A configured source that has not yielded a first feature is absent from fusion snapshots and can appear in missing_modalities.
- A configured modality that has yielded features but is still below baseline minimum remains present but anomalous status is unknown; reduced confidence is the public coverage signal.
- If a source path is invalid, that modality loop logs and exits while the global demo session remains marked running. There is no explicit per-source error field in DemoStatusOut and no nested freshness timestamp in a modality block.
- Once a modality has emitted features, its last rich feature block can continue appearing in telemetry even after that reader exits. The frontend must not treat the presence of a block alone as proof of fresh data.

## 3. Repository map

The checkout root contains:

~~~text
backend/                 FastAPI application, processing, persistence, tests
  app/
    api/                 REST routes and WebSocket route
    anomaly/             baseline estimator, statistical detector, Isolation Forest
    core/                settings and structured logging
    database/            SQLAlchemy models/session; SQLite runtime DB
    datasets/            scanner, manifest model, registry sync
    devices/             hardware discovery and registry sync
    fusion/              evidence-level fusion and temporal smoothing
    models/              Pydantic REST/WebSocket schemas
    pipelines/
      common/            source interfaces, sliding windows, octave bands
      thermal/           video/camera readers and thermal features/analyzer
      vibration/         IMS/DAQ readers and vibration features/analyzer
      acoustic/          WAV/microphone readers and acoustic features/analyzer
    services/            demo session runner and WebSocket telemetry hub
    main.py              FastAPI assembly, CORS, DB startup
  tests/                 backend pytest modules (10 files; docs report 66 tests)
  requirements*.txt     pinned runtime and development dependencies
  pytest.ini             pytest Python path configuration

frontend/                 React dashboard
  src/
    components/           Connection badge, demo controls, charts, modality UI, timeline
    services/             hand-written REST client and WebSocket hook
    types/                frontend DTO interfaces mirroring backend schemas
    assets/               Vite scaffold asset
    App.tsx               single-page orchestration/shell
    main.tsx              React bootstrap/StrictMode
    index.css             Tailwind import and dark base styles
  public/                 favicon
  package.json            npm scripts/dependencies
  package-lock.json       npm lockfile (lockfile v3)
  vite.config.ts          Vite server and /api and /ws proxies
  postcss.config.js       Tailwind v4 PostCSS plugin
  tsconfig*.json          TypeScript project configuration

data/manifests/           tracked scanner output (raw datasets are not tracked)
docs/                     API, architecture, dataset findings, development history
scripts/scan_datasets.py  scanner CLI; writes manifest and DB registry rows
run_idea_lab.bat          Windows one-click local launcher
README.md                 product/layout/local-start guidance
dataset_structure.txt     large tracked dataset directory snapshot/reference
deep-research-report.md   research/reference document, not runtime code
~~~

Important generated or externally supplied material:

- data/manifests/dataset_manifest.json is generated by the scanner but tracked. Its current absolute paths begin with C:\Users\VNAV-PC\Desktop\MECHANICAL\..., not this checkout’s path; it is stale/non-portable until regenerated.
- Raw DATASET/ and VIDEO/ directories are intentionally ignored and absent from this fresh checkout. A fresh clone cannot run the complete real-data demo until those assets are supplied.
- backend/idealab.db, backend/logs/, model artifacts, Python caches, frontend/node_modules/, and frontend build/cache output are generated/ignored.
- dataset_structure.txt and deep-research-report.md are reference material, not application logic.

## 4. Runtime architecture and configuration

### Backend runtime

backend/app/main.py creates a FastAPI app, initializes the SQLite schema in the lifespan startup hook, installs CORS, and includes all route modules. Default API host/port are 0.0.0.0:8000. Database defaults to <repo>/backend/idealab.db; logs default to <repo>/backend/logs/.

backend/app/core/config.py uses Pydantic Settings with env_prefix=IDEALAB_, .env support, and extra=ignore. Tunable environment variables cover API host/port, CORS origins, paths, processing rates/windows, FFT/MFCC/octave settings, baseline/anomaly thresholds, temporal smoothing/persistence, and demo playback speed. No .env.example is committed.

The concrete settings fields therefore map to IDEALAB_APP_NAME, IDEALAB_ENVIRONMENT, IDEALAB_REPO_ROOT, IDEALAB_DATA_DIR, IDEALAB_DATASET_DIR, IDEALAB_VIDEO_DIR, IDEALAB_MANIFEST_DIR, IDEALAB_MODELS_DIR, IDEALAB_DB_PATH, IDEALAB_LOG_DIR, IDEALAB_THERMAL_PROCESSING_FPS, IDEALAB_THERMAL_HOTSPOT_PERCENTILE, IDEALAB_VIBRATION_WINDOW_SECONDS, IDEALAB_VIBRATION_WINDOW_OVERLAP, IDEALAB_VIBRATION_DEFAULT_SAMPLE_RATE, IDEALAB_AUDIO_WINDOW_SECONDS, IDEALAB_AUDIO_WINDOW_OVERLAP, IDEALAB_AUDIO_DEFAULT_SAMPLE_RATE, IDEALAB_FFT_SIZE, IDEALAB_STFT_HOP, IDEALAB_MFCC_N_COEFFS, IDEALAB_OCTAVE_MODE, IDEALAB_BASELINE_MIN_OBSERVATIONS, IDEALAB_ANOMALY_Z_THRESHOLD, IDEALAB_HEALTH_SMOOTHING_ALPHA, IDEALAB_ANOMALY_PERSISTENCE_FRAMES, IDEALAB_ANOMALY_CLEAR_FRAMES, IDEALAB_DEMO_PLAYBACK_SPEED, IDEALAB_API_HOST, IDEALAB_API_PORT, and IDEALAB_CORS_ORIGINS. Pydantic Settings reads these from .env or the process environment and ignores unknown keys.

Default CORS origins are http://localhost:5173 and http://127.0.0.1:5173. There is no production deployment configuration, migration framework, or alternate database service.

Settings initialization creates the configured data directory, manifest directory, models directory, and log directory if they do not exist. It does not create raw DATASET/ or VIDEO/ assets.

### Frontend runtime

The frontend is React 19 + TypeScript + Vite 8. Recharts provides all charts. Tailwind CSS v4 is imported through PostCSS. The package manager is npm; only frontend/package-lock.json is present. There is no router, global state library, query/cache library, form library, frontend environment-variable layer, or frontend test setup.

Vite proxies:

- /api to http://127.0.0.1:8000
- /ws to ws://127.0.0.1:8000 with WebSocket support

The current frontend uses relative REST/WS URLs, so a production deployment needs a same-origin reverse proxy or a future configurable backend URL.

### Dependencies and scripts

Backend runtime requirements are pinned in backend/requirements.txt. backend/requirements-dev.txt adds pytest and httpx. There is no pyproject.toml, setup.py, Pipfile, Dockerfile, or Makefile.

Frontend scripts (frontend/package.json):

- npm run dev — Vite development server.
- npm run build — tsc -b && vite build.
- npm run lint — oxlint.
- npm run preview — Vite preview server.

The repository documents Python 3.13.14, Node 24.18.0, npm 11.16.0, and Git 2.55.0 from the original development environment. These are documentation observations, not enforced version files.

### Tests and verification

Backend tests are in backend/tests/ and cover foundation/API behavior, dataset scanning, thermal/vibration/acoustic pipelines, anomaly detection, fusion, demo runner, devices, and octave bands. docs/DEVELOPMENT.md reports 66/66 passing. Dataset integration tests are conditional on raw directories being available. There are no frontend test files or test script. Frontend verification is currently intended to be TypeScript/Vite build and lint oriented; in this checkout node_modules is absent, so packages were not installed and frontend commands were not run during this analysis.

## 5. Backend/API contract

All REST handlers are implemented under backend/app/api/. Pydantic DTOs are in backend/app/models/schemas.py; ORM source fields are in backend/app/database/models.py.

### Contract summary

| Method and route | Request | Response | Errors/notes | Implementation |
|---|---|---|---|---|
| GET /api/health | none | {status, app, environment} | Process health only; does not probe DB/devices | routes_health.py |
| GET /api/machines | none; no pagination | MachineOut[] | Ordering unspecified | routes_machines.py |
| POST /api/machines | MachineCreate; only machine_name required | 201 MachineOut | Pydantic 422; no duplicate-name rule | routes_machines.py |
| GET /api/machines/{machine_id} | path ID | MachineOut | 404 detail Machine not found | routes_machines.py |
| GET /api/machines/{machine_id}/status | path ID | MachineHealthState | 404; honest unknown before history | routes_machines.py |
| GET /api/machines/{machine_id}/history?limit=200 | path ID; raw limit | newest-first history records | 404; score/confidence nullable | routes_machines.py |
| GET /api/machines/{machine_id}/events?limit=50 | path ID; raw limit | newest-first event records | 404; resolved_at nullable | routes_machines.py |
| GET /api/datasets | none | DatasetInfo[] | empty until scanner/registry run | routes_datasets.py |
| GET /api/devices | none | DeviceStatusOut[] | probes synchronously on every call | routes_devices.py |
| POST /api/demo/start | DemoStartRequest | DemoStatusOut | 409 if singleton running; paths/machine not validated | routes_demo.py / demo_runner.py |
| POST /api/demo/stop | none | DemoStatusOut running:false | safe/no-op when stopped | routes_demo.py / demo_runner.py |
| GET /api/demo/status | none | singleton DemoStatusOut | no per-machine query | routes_demo.py / demo_runner.py |

There is no implemented REST endpoint for baseline detail/reset/progress, live-session start, machine update/delete, device assignment, raw frames/spectrograms, or WebSocket subscriptions.

### Health

GET /api/health (backend/app/api/routes_health.py) returns:

~~~json
{"status":"ok","app":"IDEA LAB","environment":"development"}
~~~

app and environment come from settings. A successful response does not prove that the database, datasets, devices, or monitoring session are healthy.

### Machines

MachineCreate fields:

~~~json
{
  "machine_name": "Pump A",
  "machine_type": null,
  "manufacturer": null,
  "model": null,
  "rpm": null,
  "rated_power": null,
  "location": null,
  "sensor_configuration": null
}
~~~

MachineOut adds machine_id, baseline_status, monitoring_status, and created_at. sensor_configuration is nullable JSON and present in the backend response, although the current frontend Machine interface omits it. baseline_status starts as not_calibrated and becomes calibrated when any modality baseline is persisted. monitoring_status defaults to stopped and the demo runner never updates it, so it is not an authoritative live-session indicator.

### Machine status

GET /api/machines/{id}/status returns MachineHealthState. Before any health history exists, it deliberately returns:

~~~json
{
  "machine_id": "<id>",
  "timestamp": "<machine-created-at>",
  "health_score": null,
  "status": "unknown",
  "severity": null,
  "confidence": null,
  "modality_contributions": {},
  "missing_modalities": ["thermal", "vibration", "acoustic"],
  "evidence": [],
  "model_version": null
}
~~~

After history exists, the route maps the newest HealthHistory row and reconstructs evidence/contributions from its JSON. Because the history table does not store missing modalities, severity, or model version, those fields are not fully recoverable from a persisted row.

### Machine history

GET /api/machines/{id}/history?limit=200 returns newest-first records:

~~~json
{
  "timestamp": "<datetime>",
  "health_score": "<number-or-null>",
  "status": "normal|warning|critical|unknown",
  "confidence": "<number-or-null>"
}
~~~

The frontend must reverse the array for chronological charts if desired. The endpoint has no cursor/range pagination and does not include evidence, severity, or missing modalities.

### Machine events

GET /api/machines/{id}/events?limit=50 returns newest-first:

~~~json
{
  "event_id": "<uuid>",
  "started_at": "<datetime>",
  "resolved_at": "<datetime-or-null>",
  "severity": "<string>",
  "modality_contributions": {"vibration": "<number>"},
  "evidence": {
    "evidence": [
      {
        "modality": "thermal|vibration|acoustic",
        "feature": "<string>",
        "value": "<number-or-null>",
        "baseline_mean": "<number-or-null>",
        "deviation": "<number-or-null>",
        "note": "<string-or-null>"
      }
    ]
  }
}
~~~

The evidence value is a wrapper object, not a bare array. resolved_at:null means the persisted event is ongoing. Events are created only after temporal persistence, not on a single abnormal frame.

### Datasets

GET /api/datasets returns the database registry as DatasetInfo[]. It is empty until scripts/scan_datasets.py runs. Each item contains dataset_id, dataset_name, nullable machine_type, modality, path, nullable format, sample_count, sample_rate, channels, normal_count, anomaly_count, and notes.

The route intentionally does not expose scanner-only duration_seconds, label_categories, manifest_path, or scanned_at. Paths are provenance strings and can be absolute paths from another machine. Dataset scanning is a separate CLI action, not API-startup behavior.

### Devices

GET /api/devices calls sync_devices() on every request. Discovery probes OpenCV camera indices 0..2; it always returns an honest not_connected vibration sensor and microphone because no DAQ/audio backend is integrated. Device statuses are connected, not_connected, or error in the public schema. The backend response includes nullable machine_id, nullable connection_type, optional JSON configuration, and nullable last_seen.

The registry does not remove rows that disappear from a later probe, so a stale connected row is possible. last_seen is the probe timestamp, not proof that a device is producing telemetry. The current frontend type omits configuration and collapses error and not_connected visually.

### Demo lifecycle

DemoStartRequest:

~~~json
{
  "machine_id": "<id>",
  "thermal_source": "<absolute-mp4-path-or-null>",
  "vibration_source": "<ims-test-directory-or-null>",
  "vibration_channel": 0,
  "acoustic_source": "<wav-path-or-null>",
  "playback_speed": 1.0
}
~~~

Only machine_id is required by Pydantic. POST /api/demo/start creates a DB session before starting modality tasks. It does not verify the machine ID or source paths. A global singleton prevents concurrent sessions (409 with detail A demo session is already running). A non-positive playback speed is accepted by the schema layer and clamped internally to at least 0.01.

DemoStatusOut:

~~~json
{
  "running": true,
  "machine_id": "<id-or-null>",
  "session_id": "<id-or-null>",
  "mode": "demo",
  "sources": {
    "thermal": "<string-or-null>",
    "vibration": "<string-or-null>",
    "acoustic": "<string-or-null>"
  },
  "started_at": "<datetime-or-null>"
}
~~~

POST /api/demo/stop cancels loops, closes readers, ends the MonitoringSession, and returns stopped status. Calling it while stopped is allowed. GET /api/demo/status reports the singleton only; it cannot list multiple machines/sessions. Invalid source paths can leave running:true while one modality silently exits, so the frontend needs a stalled/no-fresh-telemetry state.

## 6. WebSocket/live telemetry contract

### URL and lifecycle

The implemented route is WS /ws/telemetry (backend/app/api/websocket.py). In local development, Vite proxies it to ws://127.0.0.1:8000/ws/telemetry. The server accepts the connection, stores it in a global TelemetryHub set, waits for client text only to detect disconnects, and broadcasts JSON to every connected client. There is no subscription, machine filter, initial snapshot, heartbeat payload, server-side reconnect protocol, or error-message contract.

Current emission is DEMO MODE only. The Pydantic schema reserves mode:live, but no live runner emits it. The fusion loop broadcasts approximately once per second after at least one active modality has produced a feature snapshot. If no modality has produced a snapshot, it skips the broadcast. Modality readers run at their own processing cadence; playback speed changes source consumption, not the approximately one-second fusion cadence.

### Payload shape

The following is a field-shape example based on TelemetryPayload plus the rich feature models assembled in backend/app/services/demo_runner.py. Angle-bracket values are placeholders for actual numeric/string values; they are not fabricated measurements.

~~~json
{
  "timestamp": "<datetime>",
  "machine_id": "<machine-id>",
  "mode": "demo",
  "thermal": {
    "source": "<string>",
    "mean_intensity": "<number>",
    "max_intensity": "<number>",
    "min_intensity": "<number>",
    "std_intensity": "<number>",
    "hotspot_threshold": "<number>",
    "hotspot_pixel_count": "<integer>",
    "hotspot_area_fraction": "<number>",
    "hotspot_centroid_x": "<number-or-null>",
    "hotspot_centroid_y": "<number-or-null>",
    "gradient_mean": "<number>",
    "gradient_max": "<number>",
    "is_radiometric": false
  },
  "vibration": {
    "source": "<string>",
    "rms": "<number>",
    "variance": "<number>",
    "std": "<number>",
    "peak": "<number>",
    "peak_to_peak": "<number>",
    "crest_factor": "<number>",
    "kurtosis": "<number>",
    "skewness": "<number>",
    "dominant_frequency": "<number>",
    "spectral_centroid": "<number>",
    "spectral_bandwidth": "<number>",
    "spectral_peaks": [{"frequency": "<number>", "magnitude": "<number>"}],
    "band_energies": {
      "band_type": "octave|third_octave",
      "bands": [{
        "center_frequency": "<number>",
        "low_frequency": "<number>",
        "high_frequency": "<number>",
        "energy": "<number>"
      }]
    },
    "analysis_type": "generic_spectral|bearing_specific",
    "bearing_fault_frequencies": {
      "bpfo": "<number>",
      "bpfi": "<number>",
      "bsf": "<number>",
      "ftf": "<number>"
    }
  },
  "acoustic": {
    "source": "<string>",
    "rms": "<number>",
    "peak_amplitude": "<number>",
    "crest_factor": "<number>",
    "energy": "<number>",
    "dominant_frequency": "<number>",
    "spectral_centroid": "<number>",
    "spectral_bandwidth": "<number>",
    "spectral_rolloff": "<number>",
    "spectral_flatness": "<number>",
    "spectral_peaks": [{"frequency": "<number>", "magnitude": "<number>"}],
    "band_energies": {
      "band_type": "octave|third_octave",
      "bands": [{
        "center_frequency": "<number>",
        "low_frequency": "<number>",
        "high_frequency": "<number>",
        "energy": "<number>"
      }]
    },
    "mfcc": ["<number>"]
  },
  "health": {
    "machine_id": "<machine-id>",
    "timestamp": "<datetime>",
    "health_score": "<number-or-null>",
    "status": "normal|warning|critical|unknown",
    "severity": "<string-or-null>",
    "confidence": "<number-or-null>",
    "modality_contributions": {"<modality>": "<number>"},
    "missing_modalities": ["thermal|vibration|acoustic"],
    "evidence": [{
      "modality": "thermal|vibration|acoustic",
      "feature": "<string>",
      "value": "<number-or-null>",
      "baseline_mean": "<number-or-null>",
      "deviation": "<number-or-null>",
      "note": "<string-or-null>"
    }],
    "model_version": "<string-or-null>"
  },
  "events": [
    {"type": "event_started", "status": "warning|critical"},
    {"type": "event_cleared"}
  ]
}
~~~

The actual schema permits thermal, vibration, acoustic, and health to be null. band_energies is nullable in the backend VibrationFeatures model, even though the current frontend interface declares vibration band data as required; a redesign should preserve backend nullability. bearing_fault_frequencies is nullable and is normally null in current demo runs. Thermal centroids are nullable. Events default to an empty list and are sparse transition notifications, not a complete active-event state.

There is no nested modality timestamp or freshness flag. A displayed modality block therefore needs a frontend last-message/stale indicator based on the envelope timestamp and connection timing, not an assumption that the block is fresh.

### Multi-client/multi-machine behavior

The backend supports multiple WebSocket connections but broadcasts the same global stream to all of them. There is no server-side machine subscription/filter and only one global demo session. The frontend must ignore/filter payloads whose machine_id does not match the currently selected machine, and it must not present the architecture as simultaneous multi-machine live monitoring.

## 7. Existing frontend architecture

### Application structure

The frontend is one App.tsx shell with local useState/useEffect. It has no router or page-level navigation. App calls health, machines, devices, and datasets once on mount; owns machine creation and active demo machine state; opens one telemetry hook; and composes the dashboard components.

frontend/src/services/api.ts is a hand-written typed fetch wrapper. frontend/src/services/useTelemetry.ts creates one WebSocket at /ws/telemetry. frontend/src/types/index.ts contains TypeScript DTOs intended to mirror the Pydantic schemas.

### Current data flow

1. App.tsx mounts and fetches /api/health, /api/machines, /api/devices, and /api/datasets.
2. useTelemetry() opens one WebSocket and stores the latest JSON-cast payload.
3. DemoPanel polls /api/demo/status every three seconds and calls demo start/stop.
4. Every telemetry envelope updates latest in App.
5. HealthTrendChart and EventTimeline receive a refreshKey derived from the telemetry timestamp and refetch their full REST collections on every telemetry message.
6. Modality charts render feature arrays from the most recent envelope.

### Framework/build/styling/chart choices

- Framework: React 19.
- Language: TypeScript with strict/no-unused compiler options.
- Build/dev server: Vite 8.
- Styling: Tailwind CSS v4 via PostCSS plus a small index.css dark base.
- Charts: Recharts (LineChart, BarChart, ResponsiveContainer, tooltips/axes).
- State: component-local React state only.
- Routing: none.
- REST: custom fetch wrapper.
- Realtime: custom WebSocket hook.

### Current REST coverage

api.ts has wrappers for all implemented routes except it does not use the individual machine GET from the UI. machineStatus() exists but is unused. Request errors discard backend response bodies and most component failures are silently swallowed. There are no abort/timeout controls, query caching, or structured error type.

### Current WebSocket coverage

The hook reports only connecting | open | closed, blindly casts parsed JSON to TelemetryPayload, ignores malformed JSON, and closes on cleanup. It has no reconnect/backoff, stale-message protection, last-message time, heartbeat, payload schema validation, machine filtering, or explicit error detail.

## 8. Component audit

| Component/file | Current responsibility and data | Reusability / redesign disposition |
|---|---|---|
| frontend/src/App.tsx | Single dashboard shell; initial health/machine/device/dataset loads; machine creation; active demo machine; telemetry composition | Keep orchestration conceptually, but split into app shell, overview/machine pages, data hooks, and explicit selection state. |
| frontend/src/components/ConnectionBadge.tsx | Presentational colored pill for API/WS/demo/device states | Keep the concept; refactor to accessible status semantics and independent API, WebSocket, demo, device, stale, and unknown states. |
| frontend/src/components/DemoPanel.tsx | Manual source path/channel/playback controls, status polling, start/stop, compact live health/evidence | Keep the capability, split controls from health summary; add pending/error/stale/calibration/source-health states. Use nullable-safe confidence rendering. |
| frontend/src/components/HealthTrendChart.tsx | Fetches /history, reverses rows, renders Recharts line chart | Keep chart concept; move fetching into a shared/cached history hook and refresh only on selection/event/timed policy, not every telemetry tick. Add null/empty/loading/error/accessibility handling. |
| frontend/src/components/EventTimeline.tsx | Fetches /events and renders persisted start/resolution/contribution summaries | Keep timeline concept; centralize data ownership, preserve ongoing resolved_at:null, refresh on meaningful event changes, and expose evidence details. |
| frontend/src/components/ModalityDetails.tsx | Tabs for available vibration/acoustic/thermal blocks; metric readouts; spectral/band/MFCC charts; thermal non-radiometric note | Keep modality-detail concept but likely replace dense single component with independent modality panels and honest unavailable/calibrating states. Add contributions/evidence/freshness and null-safe guards. |
| frontend/src/components/BandEnergyChart.tsx | Reusable octave/third-octave bar chart | Keep and harden for nullable/empty data, dense labels, responsive sizing, keyboard/accessible alternatives. |
| frontend/src/components/SpectralPeaksChart.tsx | Reusable dominant spectral-peak bar chart | Keep concept; add empty states, labels/units, and text alternative. |
| frontend/src/services/api.ts | Typed REST boundary for all current routes | Keep boundary; add configurable base URL, structured backend errors, abort/timeout, request state, and exact nullable types. |
| frontend/src/services/useTelemetry.ts | One WebSocket lifecycle/latest-payload hook | Keep abstraction; replace with reconnect/backoff, validation, freshness metadata, machine filtering, and explicit error/closed/stale state. |
| frontend/src/types/index.ts | Central frontend DTO definitions | Keep as a single source; align with backend nullability (vibration.band_energies, configuration fields) and distinguish backend health state from local connection state. |
| frontend/src/main.tsx | StrictMode + React root bootstrap | Keep. |
| frontend/src/index.css | Tailwind import, global dark palette/body defaults | Keep as a base only; redesign typography/layout/theme. |
| frontend/src/assets/vite.svg | Unused scaffold asset | Safe to replace/remove in redesign; not a product data source. |

## 9. Data ownership matrix

| Data / feature | Source of truth | How frontend receives it | Frontend responsibility |
|---|---|---|---|
| Machine information | SQLite Machine model; routes_machines.py | GET /api/machines, GET /api/machines/{id}, POST /api/machines | Display metadata, select machine, submit creation; preserve nullable fields and do not infer monitoring state from stale monitoring_status. |
| Health score | FusionEngine + TemporalHealthTracker | health.health_score in WebSocket; latest status endpoint/history | Display nullable score and smoothing timestamp; never recalculate or turn null into zero. |
| Health status | FusionEngine / persisted HealthHistory | WebSocket health.status; /status, /history | Display exactly normal, warning, critical, or unknown; unknown is not healthy. |
| Confidence | FusionEngine calibrated-modality coverage | WebSocket health; /status/history | Show as evidence coverage, not probability; preserve null/0.0 distinction. |
| Modality contributions | Fusion MachineHealthState.modality_contributions; persisted in history/event evidence | WebSocket health; /status; /events | Visualize backend-provided values; no client weighting or averaging. |
| Vibration metrics | VibrationAnalyzer rich VibrationFeatures | WebSocket vibration block | Render fields/units/charts; honor nullable band data and generic-vs-bearing analysis type. |
| Acoustic metrics | AcousticAnalyzer rich AcousticFeatures | WebSocket acoustic block | Render scalar metrics, spectral peaks, bands, MFCC; do not infer labels beyond backend fields. |
| Thermal metrics | ThermalAnalyzer/ThermalFeatures | WebSocket thermal block | Label relative intensity unless is_radiometric is true; preserve nullable hotspot centroids. |
| Anomalies/evidence | Statistical detector/Isolation Forest + Fusion engine | WebSocket health.evidence; persisted event evidence | Show feature, deviation, value, notes, and provenance; do not diagnose beyond evidence. |
| Events | TemporalHealthTracker and AnomalyEvent DB rows | WebSocket sparse transitions; GET /events | Render starts/resolutions/ongoing state; do not treat one abnormal frame as a persisted event. |
| History | HealthHistory DB rows | GET /api/machines/{id}/history newest-first | Reverse for chronology, handle null scores, avoid per-frame refetch storms. |
| Device connectivity | devices.discovery + DeviceDefinition registry | GET /api/devices (re-probes every call) | Preserve connected/not_connected/error, show notes/configuration, and distinguish probe time from data freshness. |
| Datasets | Scanner output + DatasetRegistry DB | GET /api/datasets; scanner manifest is not directly served | Show registry metadata and honest empty state; warn that paths may be stale/absolute and data is not guaranteed local. |
| Demo state | Singleton DemoRunner + MonitoringSession | GET /api/demo/status, start/stop responses | Treat this as authoritative session state; show DEMO MODE prominently; surface a modality stall when sources fail silently. |
| Calibration/baseline state | Baseline rows and Machine.baseline_status; detector reasons | Machine list/status plus WebSocket evidence notes | Explain not_calibrated, calibrated, and unknown/needs-N evidence. Do not invent a backend calibrating enum or progress percentage. |

## 10. Honest-state rules

The backend intentionally distinguishes several states. The frontend must preserve those distinctions:

1. Health status is exactly normal | warning | critical | unknown (backend/app/models/schemas.py). unknown means there is not enough usable evidence, not “healthy but quiet.”
2. Device status is exactly connected | not_connected | error. A missing DAQ/microphone backend is not_connected, never a fabricated connected state.
3. Missing modality is represented by health.missing_modalities when no current snapshot is present. A source that has not emitted its first feature may be temporarily missing.
4. Baseline insufficiency is an unknown anomaly/health condition plus evidence notes such as No baseline yet or needs 30. The frontend may present this as “calibrating/insufficient baseline” in explanatory copy, but there is no literal backend calibrating status.
5. Machine calibration is the coarse string not_calibrated/calibrated; calibrated means at least one modality baseline is saved, not that all three are ready.
6. Thermal calibration is is_radiometric. Current readers return false. Intensity values, hotspot threshold, and gradients must not be shown as degrees Celsius.
7. Null is meaningful. health_score, confidence, evidence values/deviations, thermal centroids, and bearing fault frequencies can be null. Do not coerce null to 0 or a connected/healthy status.
8. Confidence is coverage, not probability. It is calibrated modality count divided by three. Show it adjacent to health score and missing/unknown modality explanations.
9. Score can be null while status is unknown. Fusion all-unknown states use health_score:null; the pre-history status endpoint also uses confidence:null, while a telemetry all-unknown state sets confidence 0.0. Keep these distinctions.
10. Demo is not live. mode:demo, source strings, and the DEMO MODE behavior must not be presented as connected hardware or production monitoring.
11. Vibration analysis honesty. Current demo has analysis_type:generic_spectral and bearing_fault_frequencies:null; do not imply BPFO/BPFI/BSF/FTF diagnosis.
12. No fresh data is not zero data. A modality block can remain present after its reader stops, with no nested freshness flag. Use envelope/connection timestamps and show stale state rather than displaying old values as live.
13. Machine monitoring_status is not authoritative. The demo runner leaves it at stopped; use /api/demo/status for singleton session state.
14. Dataset registry is not proof of local availability. It is empty until scanning runs, and the committed manifest contains absolute paths from the original development machine.
15. Events are confirmed transitions. A single warning/critical frame is not a persisted event; start requires five abnormal frames and clear requires eight normal/unknown frames.

## 11. Performance and technical risks

### Frontend risks

- REST polling storm: App.tsx derives a timestamp refreshKey from every WebSocket message, causing HealthTrendChart.tsx and EventTimeline.tsx to fetch complete history/events about once per second. This adds avoidable DB/API load and can produce out-of-order state overwrites.
- No WebSocket reconnect: useTelemetry.ts transitions permanently to closed on close/error. A backend restart or transient network failure requires a page reload.
- Stale callbacks/lifecycle: WebSocket callbacks are not guarded against an old socket updating state after cleanup; React StrictMode development effects can expose duplicate open/close behavior.
- No machine filtering: the frontend renders the latest global payload regardless of machine_id. A selected machine can show another machine’s telemetry if a future client/session arrangement produces it.
- Unsafe nullable confidence: DemoPanel.tsx uses health.confidence non-null assertion; backend explicitly allows null. This can produce NaN% or an implied measurement.
- Unvalidated payload: the hook blindly casts JSON. ModalityDetails.tsx calls toFixed() on dynamic fields, and a null/missing backend field can crash rendering. The backend vibration band model is nullable while the frontend type requires it.
- Stale data across machine changes: history/event arrays are not cleared on selection changes; failed requests preserve old data and there are no request identity/abort guards.
- Silent failures: initial API failure, demo-status polling failures, history/events failures, and stop failures are mostly swallowed. Empty UI can look like a valid empty system rather than an error or unavailable state.
- Incomplete machine selection: machine rows are not interactive. machineStatus() is defined but unused; historical views only appear while a demo is active.
- Missing loading/empty/stale states: most components jump between data/no-data without request-pending, stale, source-failed, calibration, or retry states.
- Responsive layout: modality statistics use forced four-column grids; fixed 100–140px chart heights and dense labels can collide on narrow screens; header badges do not have a wrapping plan.
- Accessibility: inputs rely on placeholders instead of labels; modality tabs lack tab roles/selection semantics; chart values have no text alternative; color is the primary status channel; status changes are not announced; focus-visible treatment is not explicit. frontend/index.html still has the template title frontend.
- No frontend automated tests: regressions in contract handling, state transitions, and responsive/accessibility behavior are not covered by repository tests.

### Backend/contract risks that affect the frontend

- POST /api/demo/start accepts nonexistent machine IDs and invalid paths, then can leave a session running while a source loop exits silently.
- The demo runner is a global singleton. The WebSocket is global broadcast, not machine-scoped; multi-machine UI requires backend changes for true isolation.
- Machine.monitoring_status is not updated on demo start/stop.
- GET /api/devices performs synchronous camera probing on every call; frequent polling would block and may be expensive.
- Device rows are not deleted when a device disappears, so a stale connected record may exist.
- No per-modality freshness/error field is emitted after a reader exits.
- History/events have raw limits but no range/cursor pagination and return newest-first.
- Health history drops missing-modality/severity/model-version fields.
- Persisted baseline statistics do not persist the Isolation Forest object.
- Raw datasets and videos are external/ignored; a fresh clone cannot provide a real demo without them.
- The tracked manifest contains machine-specific absolute paths.

## 12. Frontend opportunities

### A. Fully supported by current backend data

- System availability card from /api/health with the caveat that it is process health only.
- Machine registry: list/create/detail metadata, nullable machine fields, baseline status display.
- Current health overview: score, exact status, severity, evidence coverage/confidence, missing modalities, model version.
- Modality panels for all current rich telemetry fields: vibration time/frequency features, acoustic scalar/frequency/MFCC features, thermal intensity/hotspot/gradient features.
- Octave/third-octave band charts and spectral-peak charts from the payload.
- Generic-spectral honesty messaging and optional bearing-frequency display only when backend supplies it.
- Relative thermal intensity view and explicit non-radiometric note.
- Health history chart from /history, with newest-first reversal and null-safe points.
- Persisted anomaly-event timeline from /events, including ongoing (resolved_at:null) and resolved events, contributions, and evidence.
- Device status inventory from /devices, including real probe status and backend notes/configuration.
- Dataset registry summary from /datasets, including modality, sample counts/rates/channels, label counts, notes, and an honest empty state.
- Demo controls and singleton state through /demo/start, /demo/stop, /demo/status, clearly labeled dataset-driven simulation.

### B. Partially supported; frontend can expose only a constrained view

- Calibration: the UI can show not_calibrated, calibrated, unknown reason text, and “waiting for at least 30 observations,” but cannot show authoritative per-modality progress, reset, or completion controls.
- Machine detail/navigation: REST supports individual machine/status/history, but the current UI has no router/selection model, no update/delete routes, and the WebSocket is not machine-scoped.
- Live monitoring: the schema reserves mode:live and thermal camera probing exists, but DAQ and microphone capture are not implemented; do not promise a live mode that can actually stream all modalities.
- Thermal visualization: metrics and provenance are available, but no frame/image bytes, playback URL, or temperature map are in telemetry. A UI can show metric cards, not a live thermal image without backend work.
- Event UX: transition events and persisted rows are available, but there is no continuous active-event boolean, source-level error, or historical missing-modality data.
- Dataset-to-demo flow: registry metadata is available, but the start API accepts manual absolute paths and does not expose source selection/browse or path validation.
- Device association: device responses contain nullable machine_id, but discovery does not provide assignment endpoints or reliable historical status.
- Evidence exploration: current evidence is enough for a table/detail drawer, but baseline means are often null and the backend does not expose full baseline distributions.

### C. Requires backend changes

- True multi-machine monitoring or machine-scoped WebSocket subscriptions.
- Reliable LIVE MODE for vibration DAQ and microphone capture.
- Validated source-picker/upload/discovery APIs and per-source startup/error/freshness status.
- Per-modality calibration progress, pause/reset/approve-baseline controls, and a public baseline detail endpoint.
- Persisted/reloaded Isolation Forest model state if model continuity across restart is required.
- Calibrated thermal temperatures, radiometric frames, or image/ROI streams.
- Raw historical modality series/spectrograms/thermal frames beyond the current latest snapshot.
- Continuous active-event state, event acknowledgment, alert delivery, or richer event evidence.
- History fields for missing modalities, severity, model version, and modality-level state.
- Device assignment/configuration management and removal/staleness semantics.
- Pagination/filtering/range queries for large history/event collections.
- Authentication, authorization, audit logs, or multi-user tenancy.

## 13. Supported vs unsupported frontend feature boundary

| Proposed frontend capability | Current support | Safe implementation now |
|---|---|---|
| System overview | Fully supported | API availability, current demo/WS state, selected machine summary. |
| Machine overview/detail | Supported for read/create; partial for navigation/editing | Add client selection/detail views using existing list/status/history endpoints; do not claim edit/delete. |
| Health score/status | Fully supported in current/persisted forms | Display exact backend fields and null/unknown semantics. |
| Confidence/evidence | Fully supported, with semantic caveat | Present coverage ratio and evidence; never call it probability. |
| Modality contribution view | Fully supported for current state/events | Render backend contributions; do not recompute. |
| Vibration/acoustic feature analysis | Fully supported for latest telemetry | Use charts/cards; preserve nullable arrays and generic spectral label. |
| Thermal analysis | Metrics supported; calibrated temperature/image not supported | Show relative intensity/hotspot metrics and safety note. |
| Health history | Fully supported as score/status/confidence | Reverse newest-first response; accept null scores; avoid per-frame refetch. |
| Event timeline | Fully supported as persisted event records | Show ongoing/resolved and evidence wrapper; refresh on meaningful changes. |
| Device dashboard | Supported as current probe response | Distinguish connected/not connected/error and probe time; show stale-row warning if needed. |
| Dataset dashboard | Supported after scan | Show registry fields and path provenance; honest empty/unavailable state. |
| Demo controls | Fully supported for one global session | Clearly label DEMO MODE; warn that paths are not validated and modality may stall. |
| Calibration dashboard | Partial | Show coarse machine status and backend evidence reason; no invented progress/control. |
| Live sensor dashboard | Partial/schema-only | Keep future-facing affordance visibly unavailable until backend adapters exist. |
| Thermal video/temperature playback | Not supported by current telemetry | Requires backend image/temperature stream. |
| Multi-machine simultaneous live telemetry | Not supported | Requires server subscriptions/session model. |

## 14. Files that should be preserved

Preserve as source-of-truth or stable contracts during the redesign:

- Backend processing and contract files: backend/app/models/schemas.py, backend/app/api/, backend/app/services/demo_runner.py, backend/app/services/telemetry_hub.py, backend/app/fusion/, backend/app/anomaly/, backend/app/pipelines/, backend/app/database/, and backend/app/core/config.py.
- Dataset/device implementations: backend/app/datasets/, backend/app/devices/, and scripts/scan_datasets.py.
- Backend tests in backend/tests/.
- Documentation: README.md, docs/API.md, docs/ARCHITECTURE.md, docs/DATASETS.md, and docs/DEVELOPMENT.md.
- Frontend API/type boundaries as concepts: frontend/src/services/api.ts, frontend/src/services/useTelemetry.ts, and frontend/src/types/index.ts (refactor only with backend alignment).
- Reusable chart concepts: BandEnergyChart.tsx, SpectralPeaksChart.tsx, HealthTrendChart.tsx, and EventTimeline.tsx.
- Dataset manifest and scanner outputs should remain generated/reference artifacts; do not hand-edit generated metadata to make it fit a new UI.

## 15. Files likely to be redesigned

These are frontend-only candidates for the next stage; they were not changed in this analysis:

- frontend/src/App.tsx: replace single dashboard composition with application shell, selection/navigation, and page-level containers.
- frontend/src/index.css: redesign typography, layout, responsive behavior, and accessible state tokens.
- frontend/index.html: replace template title frontend with the actual product title and suitable metadata.
- frontend/src/components/DemoPanel.tsx: split source controls/status/health summary; add pending, error, stale, calibration, and source-health states.
- frontend/src/components/ModalityDetails.tsx: split into resilient modality panels with clear unknown/missing/unavailable states and contribution/evidence views.
- frontend/src/components/HealthTrendChart.tsx and EventTimeline.tsx: move data fetching upward, add caching/abort/error/loading, and use meaningful refresh triggers.
- frontend/src/components/ConnectionBadge.tsx: expand the state model and accessible semantics.
- frontend/src/services/useTelemetry.ts: reconnect/backoff/validation/freshness/filtering redesign.
- frontend/src/services/api.ts: structured errors, cancellation, configurable base URL, exact request/response DTOs.
- frontend/src/types/index.ts: align omissions/nullability with the backend.
- frontend/src/assets/vite.svg: remove or replace if the redesign no longer uses it.

No backend file should be modified as part of a frontend-only redesign unless a separately authorized backend-contract task is opened.

## 16. Recommended frontend architecture for the next stage

1. Application shell and views. Use a shell with an overview, machine detail, demo controls, devices, and datasets. A client-side router is optional but the current single-page structure needs an explicit selected-machine model.
2. Typed data layer. Keep a single REST boundary and a single telemetry stream service. Add request cancellation/timeouts, structured {status, detail} errors, loading/error/empty states, and a cache keyed by machine/resource. Do not let leaf charts own independent uncontrolled fetches.
3. Realtime store. Maintain one WebSocket connection per app, with reconnect/backoff, last-open/last-message timestamps, validation, and local machine filtering. Track connecting, open, reconnecting, closed, error, and stale separately. Since the server broadcasts globally, filter envelope machine_id on the client.
4. Backend-state vs UI-state types. Model backend health (normal|warning|critical|unknown), device status, demo status, and nullability separately from local connection/stale/loading states. Keep unknown/nullable values explicit rather than encoding them as zero.
5. Overview composition. Pair health score with status, confidence/coverage, missing modalities, calibration explanation, last telemetry timestamp, and DEMO/LIVE mode. A high score with low coverage must be visibly qualified.
6. Modality panels. Render vibration/acoustic/thermal data from a common panel contract, with modality-specific metrics/charts. Every panel needs states for no source, waiting for first sample, unknown baseline, stale last sample, and valid telemetry. Thermal copy must be relative intensity/brightness unless radiometric.
7. History/event ownership. Fetch status/history/events when machine selection changes; refresh history at a bounded interval or on meaningful event transitions, not on each telemetry tick. Reverse newest-first responses for chronology and guard against out-of-order requests.
8. Demo workflow. Keep the dataset-driven banner. Validate obvious client input (required machine, source presence, numeric ranges), but do not pretend client validation replaces backend path validation. After start, monitor telemetry freshness per modality and explain when the session is running but no fresh data arrives.
9. Charts and accessibility. Preserve Recharts initially, but provide text summaries/tables for chart data, keyboard-accessible tabs, labels for inputs, aria-live for state changes, status text in addition to color, focus-visible controls, and responsive/dense-axis handling.
10. Testing seam. Add frontend tests in the implementation stage around DTO parsing, null/unknown rendering, WebSocket reconnect/staleness, machine filtering, demo error states, and history refresh policy. None exist in the current repository.

The frontend should remain a visualization and interaction layer. Any new computation should be a display-only transformation (unit formatting, chronology reversal, label mapping), not a replacement for the backend’s health/anomaly logic.

## 17. Open questions and uncertainties

These are repository gaps, not assumptions to silently resolve during redesign:

- Which operator persona and deployment environment should the production UI target? No auth/role model is present.
- Are demo source paths expected to be local filesystem paths only, or will a future backend add uploads/browser selection?
- Should the UI show one selected machine at a time, or is true multi-machine monitoring required? The current backend supports only one global demo and broadcast telemetry.
- Is calibration intended to remain automatic-first-N, or should the product add explicit operator-controlled calibration? No endpoint currently exists.
- What is the intended stale threshold for modality telemetry? The backend provides no freshness duration, so the frontend needs a documented UI policy until a backend field is added.
- Should persisted baseline model state include Isolation Forest across restarts? Current persistence only covers statistics.
- Should thermal display recordings be shown as video/images? Current telemetry contains no image bytes or playback URL.
- Are absolute dataset paths safe to expose to users? The current API returns them, and the tracked manifest includes another machine’s paths.
- Should dataset registry be considered authoritative when the scanner has not run or when paths are stale? Current API returns an honest empty list but has no scan status endpoint.
- Are backend settings expected to be changed through .env in deployment? No .env.example or deployment contract is committed.

## 18. Exact local run commands

These are the repository-documented commands; they are instructions only and were not executed here because dependencies are intentionally not installed as part of this analysis.

### Backend first-time setup (Windows)

~~~powershell
cd G:\Hackathons\Idea Lab\repo\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
~~~

### Start backend

~~~powershell
cd G:\Hackathons\Idea Lab\repo\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
~~~

### Start frontend

~~~powershell
cd G:\Hackathons\Idea Lab\repo\frontend
npm install
npm run dev
~~~

Open http://localhost:5173. Vite proxies /api/* and /ws/* to the backend.

### Run backend tests

~~~powershell
cd G:\Hackathons\Idea Lab\repo\backend
.\.venv\Scripts\python.exe -m pytest tests/ -v
~~~

### Regenerate dataset manifest/registry (requires external raw assets)

~~~powershell
cd G:\Hackathons\Idea Lab\repo\backend
.\.venv\Scripts\python.exe ..\scripts\scan_datasets.py
~~~

The scanner reads configured DATASET/ and VIDEO/ directories, writes data/manifests/dataset_manifest.json, and upserts dataset rows in SQLite. It is not run automatically by FastAPI startup. The Windows one-click launcher is G:\Hackathons\Idea Lab\repo\run_idea_lab.bat; it checks the environment, scans datasets, starts Uvicorn/Vite, waits briefly for health responses, and opens http://localhost:5173.

### Build/lint/preview frontend

~~~powershell
cd G:\Hackathons\Idea Lab\repo\frontend
npm run build
npm run lint
npm run preview
~~~

## 19. Git/worktree status

Read-only inspection before creating this artifact showed:

~~~text
branch: main
tracking: origin/main
remote: https://github.com/NodeNexus/Multimodal-machine-health-monitoring.git
HEAD: 5469446 Update project files
status: clean; no uncommitted changes
~~~

No existing frontend work from another contributor was present in the checkout. The repository clone was created in the previously empty G:\Hackathons\Idea Lab\repo directory. The analysis artifact itself is intentionally a new untracked file under artifacts/; no application changes were made, staged, committed, reset, or discarded.
