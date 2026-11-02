# Development Log

## Phase 0 — Environment inspection

- OS: Windows 11 Pro (MSYS/Git Bash shell available)
- Python 3.13.14, pip 26.2.1
- Node v24.18.0, npm 11.16.0
- Git 2.55.0
- No NVIDIA GPU detected (`nvidia-smi` unavailable) — plan for CPU-only inference; avoid heavyweight GPU-only dependencies until/unless a GPU is available.
- 7-Zip was not installed; installed via `winget install 7zip.7zip` to extract `.7z`/`.rar` archives (IMS bearing dataset, Battery Data Set).

## Phase 1 — Foundation (complete)

Created:
- `backend/` — FastAPI app with:
  - `app/core/config.py` — all tunable parameters (window sizes, thresholds, FFT size, etc.) in one place
  - `app/core/logging.py` — structured JSON logging to stdout + file
  - `app/database/` — SQLAlchemy models (Machine, Baseline, MonitoringSession, AnomalyEvent, HealthHistory, DatasetRegistry, DeviceDefinition) + SQLite session
  - `app/pipelines/common/interfaces.py` — `ThermalInput`, `VibrationInput`, `AudioInput` ABCs and `SlidingWindowBuffer`
  - `app/models/schemas.py` — Pydantic request/response/telemetry schemas
  - `app/api/` — REST routes (`/api/health`, `/api/machines*`, `/api/datasets`, `/api/devices`, `/api/demo/*`) + `/ws/telemetry` WebSocket
  - `app/services/demo_runner.py` — demo session lifecycle (start/stop/status), persisted to DB
  - `app/services/telemetry_hub.py` — WebSocket broadcast hub
  - `app/main.py` — app assembly, CORS, DB init on startup
- `frontend/` — React + TypeScript + Vite + Tailwind v4, with:
  - `src/types/` mirroring backend Pydantic schemas
  - `src/services/api.ts` — REST client
  - `src/services/useTelemetry.ts` — WebSocket hook
  - `src/App.tsx` — dashboard shell (API/telemetry connection status, machine list + creation, device status, dataset registry summary)
- Root `.gitignore` (excludes `DATASET/`, `VIDEO/`, `node_modules/`, venvs, DB files, etc.)
- `docs/history/ARCHITECTURE.md`

Tests: `backend/tests/test_foundation.py` — 5 tests covering health endpoint, machine CRUD + status (honest "unknown" state before any processing), empty dataset/device registries, demo start/stop lifecycle (incl. 409 on double-start), and `SlidingWindowBuffer` windowing logic. All passing.

Verified end-to-end: backend (`uvicorn`) and frontend (`vite dev`) run together, Vite proxies `/api/*` and `/ws/telemetry` to the backend, REST calls and WebSocket connection both confirmed working from outside the dev server.

Datasets: extracted `IMS.7z` (vibration bearing dataset, `DATASET/IMS/IMS/{1st,2nd,3rd}_test/`) and all 6 Battery Data Set zips using a freshly installed 7-Zip. `ToyADMOS` was already extracted. Acoustic datasets (`bearing/`, `fan/`, `pump/`, `valve/`, `gearbox/`, `dev_data_pump/`) were already present as WAV + CSV. None of this has been inspected/scanned yet — that is Phase 2.

## Phase 2 — Dataset inspection (complete)

Inspected actual dataset contents before writing any scanner/training code
(see `docs/history/DATASETS.md` for full findings). Key discoveries:

- Acoustic datasets (bearing/fan/valve/gearbox/dev_data_pump): mono 16-bit
  PCM WAV @ 16kHz, ~10s clips. Two label-filename conventions found (DCASE-
  style `..._{normal|anomaly}_...` and MIMII-style `{normal|anomaly}_id_...`)
  — both handled. Train subsets are normal-only in every dataset.
- IMS vibration dataset: confirmed against the vendor README (20kHz, 20480
  points/file, 4 bearings, run-to-failure — not per-file labelled). Found
  and flagged two real discrepancies: the 3rd test set's archive internally
  extracts to a folder named `4th_test`, and its observed file count (6324)
  does not match the README's stated 4448 — both are recorded as warnings
  in the manifest rather than silently trusted.
- Thermal videos: all 8 are visible-light recordings of a thermal camera's
  display (not calibrated radiometric data) — confirmed via OpenCV frame
  inspection (resolution/fps/duration), marked `is_radiometric=False`.
- **`ToyADMOS-dataset-master/` contains zero actual audio files** — only the
  GitHub repo's scripts/spreadsheets/docs. The real audio is hosted on
  Zenodo and was never downloaded. Excluded from the scanner.
- Battery Data Set (NASA) is out of scope for this product (not thermal/
  vibration/acoustic machine data) and is intentionally not scanned.

Created:
- `backend/app/datasets/manifest.py` — `DatasetManifestEntry` schema
- `backend/app/datasets/scanner.py` — `scan_acoustic_dataset`,
  `scan_ims_vibration`, `scan_thermal_videos`, `scan_all` — all read actual
  file headers/directory contents, no hardcoded per-file paths
- `backend/app/datasets/registry.py` — writes the JSON manifest and
  upserts `DatasetRegistry` DB rows
- `scripts/scan_datasets.py` — CLI entry point
- `docs/history/DATASETS.md` — findings, written from the actual scan output
- `backend/tests/test_dataset_scanner.py` — label-parsing unit tests,
  a synthetic-WAV scan test, a missing-directory test, and an integration
  test against the real `DATASET/` directory (skipped if absent)

Verified: ran the scanner against the real downloaded data (16 datasets
registered — 5 acoustic, 3 IMS vibration sets, 8 thermal videos), confirmed
the DB rows and the discrepancy warnings, confirmed `/api/datasets` serves
the real scanned data end-to-end through a running server, and updated the
dashboard's dataset panel to show real per-dataset sample counts and
normal/anomaly splits. 8/8 new tests + 5 existing tests pass (13/13 total).

## Phase 3 — Thermal engine (complete)

Created:
- `backend/app/pipelines/thermal/readers.py` — `ThermalVideoReader` (demo,
  decodes MP4 via OpenCV, downsamples to a configurable target FPS by
  frame-stride rather than decoding+discarding at full rate) and
  `LiveThermalCamera` (live, genuinely attempts `cv2.VideoCapture(index)`;
  raises `ConnectionError` if no device is present rather than faking a
  connected state) — both implement `ThermalInput`.
- `backend/app/pipelines/thermal/features.py` — `extract_thermal_features`:
  mean/max/min/std intensity, percentile-based hotspot detection (pixel
  count, area fraction, centroid), Sobel gradient mean/max. Operates on
  relative brightness, never labelled as °C unless `is_radiometric=True`.
- `backend/app/pipelines/thermal/analyzer.py` — `ThermalAnalyzer`: stateful
  wrapper that adds frame-to-frame hotspot area change (temporal signal)
  and, only when a `ThermalBaseline` is supplied, per-feature z-score
  deviation. No baseline -> `baseline_deviation` is honestly empty, not
  zero-filled.

Bug found and fixed via testing: the initial hotspot mask used `gray >=
percentile_threshold`, which flags the *entire frame* whenever the
percentile threshold lands exactly on the dominant background value (a real
edge case with large uniform regions) — changed to strict `>`.

Tests (`backend/tests/test_thermal_pipeline.py`, 7 tests): uniform-frame
edge case, synthetic hotspot centroid localization, ROI restriction,
temporal hotspot-growth tracking, baseline deviation with/without a
baseline supplied, and a real-video integration test (skipped if `VIDEO/`
absent) that opens an actual demo MP4 and reads real frames.

Verified against real data: ran the reader+analyzer against
`VIDEO/$40,000 Thermal Camera...mp4` — mean intensity, hotspot fraction
(~2%), and centroid all vary sensibly frame-to-frame on real footage, not
just synthetic test images. 20/20 tests passing (13 previous + 7 new).

## Phase 4 — Vibration engine (complete)

Created:
- `backend/app/pipelines/common/octave.py` — reusable octave/1/3-octave
  band-energy module (built here, will be reused unchanged by the acoustic
  pipeline in Phase 5). Center frequencies follow the standard ISO base-2
  series referenced to 1kHz; verified against the standard preferred
  frequencies (31.5/63/125/.../16000 Hz) and against a pure-tone signal
  (the 1kHz band correctly captures more energy than all other bands
  combined).
- `backend/app/pipelines/vibration/features.py` — time domain (RMS,
  variance, std, peak, peak-to-peak, crest factor, kurtosis, skewness) and
  frequency domain (FFT, dominant frequency, spectral centroid/bandwidth,
  top-N spectral peaks, octave-band energy). `compute_bearing_fault_frequencies`
  (BPFO/BPFI/BSF/FTF) is a standalone function only invoked when the caller
  supplies **both** RPM and `BearingGeometry` explicitly — RPM alone does
  not trigger it, `analysis_type` stays `"generic_spectral"` otherwise.
  The IMS dataset's own bearing geometry (Rexnord ZA-2115 specifics) is
  *not* hardcoded anywhere, since the vendor README does not provide it —
  only RPM (2000) is documented, so bearing-specific analysis is available
  as a capability but disabled by default for this dataset.
- `backend/app/pipelines/vibration/readers.py` — `IMSVibrationDatasetReader`
  (demo, streams one channel, loading one ~20480-point file at a time
  rather than the whole test set) and `LiveVibrationSensor` (live, `open()`
  honestly raises `ConnectionError` since no DAQ backend is wired up).
- `backend/app/pipelines/vibration/analyzer.py` — `VibrationAnalyzer`:
  wraps the shared `SlidingWindowBuffer`, emits one `VibrationEvidence` per
  complete window, optional baseline z-score deviation.

Bug found and fixed via real-data testing: the initial FFT-based dominant-
frequency detection picked bin 0 (0 Hz) on real IMS data because the
accelerometer signal has a small DC bias — fixed by detrending (subtracting
the mean) before windowing and explicitly excluding the 0 Hz bin from
dominant-frequency/peak search.

Tests: 3 new octave-band tests + 8 new vibration tests (39 total incl.
Phases 1-3), including a real-data integration test that streams actual IMS
files. Manually verified physically-meaningful behavior across the run-to-
failure timeline on bearing 3 (channel 4) of `1st_test`: RMS 0.13 -> 0.16 ->
0.47, kurtosis 3.4 -> 3.6 -> **12.4**, crest factor 3.8 -> 4.1 -> **10.3**
from an early file to mid-run to the file just before the documented
failure — kurtosis/crest-factor spikes are the textbook signature of
bearing impulsiveness, and it shows up on the real dataset, not a synthetic
stand-in.

## Phase 5 — Acoustic engine (complete)

Created:
- `backend/app/pipelines/acoustic/readers.py` — `AudioFileReader` (demo,
  streams a WAV file via the stdlib `wave` module in blocks, downmixes
  multi-channel to mono, normalizes to [-1, 1] by the source dtype's full
  range) and `LiveMicrophone` (live, `open()` honestly raises - no capture
  backend like `sounddevice` is wired up yet).
- `backend/app/pipelines/acoustic/features.py` — `extract_acoustic_features`:
  RMS/peak/crest factor/energy, FFT-based dominant frequency/spectral
  centroid/bandwidth/rolloff/flatness/top-N peaks, **reuses the exact same
  `compute_band_energies` from Phase 4** for octave/1-3-octave bands (no
  duplicated band-analysis logic between vibration and acoustic), and MFCC
  via librosa (averaged across STFT frames within the analysis window).
  `compute_stft` is kept as a separate function (not embedded in every
  evidence payload) for future ML dataset-building or a dedicated
  spectrogram panel.
- `backend/app/pipelines/acoustic/analyzer.py` — `AcousticAnalyzer`, same
  shape as `VibrationAnalyzer` (shared `SlidingWindowBuffer`, optional
  baseline z-score deviation).
- Added `librosa` + `soundfile` to `requirements.txt` (only new heavyweight
  deps added this phase, and only because MFCC has no reasonable stdlib/
  scipy substitute).

Tests (`backend/tests/test_acoustic_pipeline.py`, 5 tests): dominant-
frequency + MFCC-shape check on a synthetic tone, a flatness check that
distinguishes white noise from a pure tone (spectral flatness must be
higher for noise), analyzer windowing + baseline deviation, live-mic
not-connected check, and a real-WAV integration test (streams an actual
bearing dataset file end-to-end through reader -> analyzer).

Verified against real data: compared a normal vs. an anomaly WAV sample
from the `bearing` dataset — crest factor (3.92 vs 4.83), dominant
frequency (2007Hz vs 100Hz), and spectral flatness (0.093 vs 0.111) all
differ, confirming the extracted features carry real discriminative signal
(a rigorous normal/anomaly comparison needs aggregate baseline statistics
across many files, which is Phase 6's job - this was a sanity check on
single real samples, not a claim of validated separability).

36/36 tests passing (31 previous + 5 new).

## Phase 6 — Baseline/anomaly engine (complete)

Created:
- `backend/app/anomaly/baseline.py` — `BaselineEstimator`: accumulates a
  bounded deque (default 5000) of full feature-dicts per observation (not
  per-feature lists), so rows stay index-aligned for model training and
  memory stays bounded regardless of monitoring duration. `compute_stats()`
  produces mean/std/p5/p95/min/max per feature; `feature_matrix()` builds
  an aligned training matrix from only the observations containing every
  requested feature.
- `backend/app/anomaly/repository.py` — persists/loads `BaselineStats`
  to/from the existing `baselines` DB table; updates `Machine.baseline_status`
  to `"calibrated"` once any modality has a saved baseline.
- `backend/app/anomaly/statistical.py` — Level 1: per-feature z-score
  against the baseline, threshold-based normal/anomalous classification
  with contributing features ranked by deviation magnitude.
- `backend/app/anomaly/isolation_forest.py` — Level 2: `IsolationForestDetector`
  wraps scikit-learn's IsolationForest, trained on a machine's own
  accumulated baseline observations. Returns `None` (not a guess) if a
  required feature is missing from the input.
- `backend/app/anomaly/detector.py` — `LayeredAnomalyDetector` combines
  both levels: returns `"unknown"` (with a reason) when no baseline exists
  or it has too few observations, otherwise runs statistical z-scoring and
  (if fitted) Isolation Forest, and flags `"anomalous"` if *either* layer
  does (favors recall - conservative for a maintenance-alerting use case).
  Level 3 (deep/learned models) is deliberately not implemented yet; the
  layering leaves room to add it as a third opinion without restructuring.

Tests (`backend/tests/test_anomaly.py`, 10 tests): baseline stat
correctness against a known synthetic distribution, feature-matrix
alignment when some observations have missing keys, statistical z-score
math, Isolation Forest inlier/outlier discrimination and missing-feature
handling, layered-detector "unknown" state, and a case showing the
Isolation Forest layer catching a joint-feature anomaly that the
statistical layer alone would miss. Also a DB round-trip test
(save -> load -> `Machine.baseline_status` updates to `"calibrated"`).

**Verified end-to-end against real data** (not just synthetic tests): built
a baseline from 150 real *normal* training WAVs from the `bearing` acoustic
dataset (rms, crest factor, spectral centroid/bandwidth/flatness, dominant
frequency, first 5 MFCCs), fit an Isolation Forest on the same features,
then evaluated on 60 held-out real *normal* test files and 60 real
*anomaly* test files:

| Group | Flagged anomalous |
|---|---|
| Normal (held-out) | 12/60 (20.0%) |
| Anomaly | 30/60 (50.0%) |

This shows real, above-chance separation (anomaly files are flagged 2.5x
more often than normal ones) but a 20% false-positive rate is far from
production-ready. This is an honest result, not a shortfall to hide: DCASE-
style machine-sound anomaly detection is a genuinely hard task even in
published research (this `bearing` dataset is a MIMII/DCASE Task 2-style
benchmark), and a first-pass statistical + Isolation Forest baseline on 6
hand-picked scalar features + 5 MFCCs is not expected to solve it. Per the
"Model Development Policy" (no claims of universal accuracy from one
successful run), this result should be read as "the engine works and
measurably discriminates," not "the anomaly detector is validated for
deployment." Improving it (more/better features, per-machine-type tuning,
proper threshold selection, eventually an autoencoder) is future work, not
blocking for the architecture to proceed.

46/46 tests passing (36 previous + 10 new).

## Phase 7 — Fusion engine + temporal fusion (complete)

Created:
- `backend/app/fusion/engine.py` — `FusionEngine.combine()`: takes a list of
  `ModalitySnapshot` (one per modality *currently streaming*) and produces
  a `MachineHealthState`. Modalities not in the snapshot list are reported
  in `missing_modalities` (sensor not streaming); modalities present but
  without enough baseline data yet are `"unknown"` and contribute nothing
  to the score but still show up as reduced `confidence`. If every present
  modality is `"unknown"`, the whole state is `"unknown"`. Health score is
  `100 * (1 - average severity)` across calibrated modalities; 2+ anomalous
  modalities (or one very severe one) escalates `"warning"` to `"critical"`.
  An Isolation Forest flag with no single feature over the z-threshold
  still contributes evidence and severity rather than being silently
  dropped. Works correctly with only one modality available (explicitly
  tested), fulfilling the "graceful with missing modalities" requirement.
- `backend/app/fusion/temporal.py` — `TemporalHealthTracker`: EWMA-smooths
  the health score, and only flips an event active/cleared after
  `persistence_frames`/`clear_frames` consecutive frames (hysteresis) - a
  single abnormal or single recovered frame does not immediately flip
  state.

Tests (`backend/tests/test_fusion.py`, 11 tests): all-unknown -> unknown
state, single-modality-available reports the other two as missing, full
3-modality normal case, single vs. double anomalous-modality
warning-vs-critical escalation, a very severe single modality also
escalating to critical, Isolation-Forest-only evidence, EWMA smoothing math,
persistence-before-raising and hysteresis-before-clearing, and a single-blip
frame correctly *not* raising an event.

**Verified end-to-end on real data across the full Phase 3-7 stack**: ran
vibration reading -> feature extraction -> baseline -> layered anomaly
detection -> fusion -> temporal smoothing over the real IMS `1st_test`
bearing-3 run-to-failure timeline (2156 files, ~36 days). First attempt
used a 40-observation baseline (files 0-40) and produced clearly wrong
early "critical" flags around file 300 - investigated rather than accepted:
crest_factor's true variability wasn't well estimated from only 40 samples
(a genuine baseline-sample-size lesson, not a code bug). Rebuilt with a
200-observation baseline (still from the dataset's stable early period) and
got a materially better, physically plausible result:

| File index (~date) | Status | Smoothed health |
|---|---|---|
| 0-750 (Oct 22 - Nov 9) | normal (one brief warning blip at #300) | 100 -> 97 |
| 900-1500 (Nov 14-19) | warning, event raised at #1050 and sustained | 86 -> 60 |
| 1650-2155 (Nov 21-25, failure) | critical, deteriorating to the end | 51 -> 13 |

The temporal tracker correctly waited for persistence before raising the
event (not triggered by the isolated #300 blip) and kept it active through
sustained degradation to the documented end-of-life failure. This is a real
finding worth remembering: **baseline sample size materially affects
reliability** - noted here and worth carrying into Phase 9's baseline UX
(the product should not let a user "complete" baseline calibration after
only a handful of observations).

57/57 tests passing (46 previous + 11 new).

## Phase 8 — Demo Mode (complete)

Rewrote `backend/app/services/demo_runner.py` to actually drive playback
instead of just tracking session state:

- Each active modality (thermal/vibration/acoustic) runs its own asyncio
  loop at its own natural cadence (`playback_speed` scales how fast each
  consumes its source; a separate fusion loop broadcasts at a steady 1s
  wall-clock interval regardless of speed, so the dashboard stays smooth).
  Sources loop back to the start on EOF so a 10s WAV clip or a 5-minute
  video can drive a long-running demo continuously.
- Per-modality baselines: loaded from the DB if already calibrated,
  otherwise **auto-bootstrapped live** from the first `baseline_min_observations`
  observations of the stream itself (matching the "normal operating
  period" workflow) - status honestly stays `"unknown"` until then, then
  an Isolation Forest is fit and the baseline is persisted.
- `backend/app/fusion/adapters.py` flattens each modality's rich feature
  model into the scalar dict the anomaly/fusion layers need.
- Every fusion cycle: evaluates anomaly per modality, calls `FusionEngine`,
  runs it through `TemporalHealthTracker`, persists a `HealthHistory` row,
  creates/resolves `AnomalyEvent` rows on event start/clear, and broadcasts
  the full `TelemetryPayload` over the existing WebSocket hub.
- Added `vibration_channel` to `DemoStartRequest`/`DemoPanel` (needed since
  IMS vibration sources are a directory + channel index, not one file).
- Frontend: `DemoPanel.tsx` - lets the user pick a machine and enter
  thermal/vibration/acoustic source paths, clearly labelled **"DEMO MODE —
  DATASET-DRIVEN SIMULATION"** in an amber banner (never implies a live
  sensor), shows live health score/status/confidence/missing-modalities/
  evidence streamed over the WebSocket while running.

Tests (`backend/tests/test_demo_runner.py`, 3 tests): uses small synthetic-
but-correctly-shaped IMS-format files (not the full multi-GB dataset, for
test speed/determinism) to verify the runner actually streams, persists at
least one `HealthHistory` row, and stops cleanly; a double-start conflict
case; and a missing-source case that must degrade gracefully (session
stays "running" but that modality's loop ends early) rather than crashing.

**Verified live against real multi-GB datasets**, not just the synthetic
test: started the full backend + a real demo session with all three real
sources at once (a real thermal MP4, the real IMS `1st_test` bearing-3
channel, a real bearing-acoustic WAV) at 20x playback speed, connected an
independent WebSocket client, and confirmed real telemetry arriving every
~1s with live-varying values across all three modalities simultaneously
(e.g. `hotspot_area_fraction`, `spectral_centroid`, `mfcc_0`), all three
baselines auto-calibrating within ~5s of playback and getting persisted,
`Machine.baseline_status` flipping to `"calibrated"`, 48 `HealthHistory`
rows and 2 `AnomalyEvent` rows accumulating in the DB, and a clean stop.
Also re-verified the whole flow through the Vite dev-server proxy (not
just talking to the backend directly) with a fresh machine and the IMS
`2nd_test` vibration source.

60/60 tests passing (57 previous + 3 new).

## Phase 9 — Dashboard (complete)

Extended telemetry and built out the detailed dashboard views:

- Backend: `_ModalityRuntime` now keeps the full feature model (not just
  the flattened scalar dict used for anomaly detection) and the fusion
  loop broadcasts it, so the dashboard gets real band-energy arrays,
  spectral peaks, MFCCs, and hotspot centroid data every cycle - not just
  the handful of scalars needed for baseline/anomaly math. Wired
  `settings.octave_mode` into both analyzers instead of a hardcoded
  `"octave"` default (configurable, not hardcoded into the frontend, per
  the octave-module requirement). Added `GET /api/machines/{id}/events`.
- Frontend: `BandEnergyChart` (reusable for vibration and acoustic octave/
  1-3-octave bars), `SpectralPeaksChart` (dominant-frequency bar chart -
  the practical "FFT graph" for a per-window snapshot), `ModalityDetails`
  (tabbed Vibration/Acoustic/Thermal panel with readouts + charts + MFCC
  bars + bearing-fault-frequency display when available + the "generic
  spectral analysis" honesty note when not), `HealthTrendChart` (health
  score over time from `/history`), `EventTimeline` (from the new
  `/events` endpoint). Lifted the single WebSocket connection to `App`
  (was duplicated between `App` and `DemoPanel`) and passed `latest`
  telemetry down as props.

Tests: added an events-endpoint test (empty list for a real machine, 404
for a missing one) to `test_foundation.py`. 61/61 tests passing (60
previous + 1 new) - Phase 9 was mostly frontend/telemetry-shape work
already covered by Phase 8's demo-runner tests plus this one new endpoint
test.

**Verified against real data through the full stack**: ran a real demo
session (IMS vibration source) through the Vite proxy, confirmed
`/api/machines/{id}/history` and `/events` both return real accumulated
data through the proxy exactly as the dashboard will call them, and
independently confirmed via a WebSocket client that a single telemetry
payload's `vibration` block now carries 14 real octave-band entries and
real spectral peaks (not just the 6 scalar features previously sent).
`npm run build` type-checks clean. Note: no browser was available in this
environment to visually confirm chart rendering - the data flowing to the
components was verified at the API/WebSocket level, but an actual visual
check in a browser is still recommended before considering the dashboard
UI final.

## Phase 10 — Live input adapters / device discovery (complete)

- `backend/app/devices/discovery.py`: `probe_thermal_cameras()` genuinely
  enumerates OpenCV `VideoCapture` indices (0-2) and reports real
  resolution/fps for anything that opens - matching how `LiveThermalCamera`
  (built in Phase 3) actually connects. `probe_vibration_sensors()` and
  `probe_microphones()` honestly return `"not_connected"` with a note
  explaining why: no DAQ or audio-capture backend is integrated yet (this
  mirrors `LiveVibrationSensor`/`LiveMicrophone`'s own honest
  `ConnectionError` behavior from Phases 4-5). Nothing here fabricates a
  connected device.
- `backend/app/devices/registry.py`: `sync_devices()` upserts probe
  results into the existing `devices` DB table, matched by
  `(device_type, identifier)` so repeated calls don't create duplicates.
- `GET /api/devices` now re-probes on every call and returns the real,
  current state instead of an always-empty placeholder.

This closes the LIVE MODE architecture loop: `LiveThermalCamera`,
`LiveVibrationSensor`, and `LiveMicrophone` (interfaces + honest
not-connected behavior) were built alongside their demo counterparts back
in Phases 3-5; Phase 10 adds the discovery/registry layer that makes them
visible to the API and (eventually) the dashboard, without requiring any
change to the processing pipelines themselves - exactly the point of the
shared `ThermalInput`/`VibrationInput`/`AudioInput` abstraction from Phase 1.

Tests (`backend/tests/test_devices.py`, 4 tests): discovery returns one
entry per device type at minimum, vibration/microphone are always honestly
`"not_connected"` with a note, `sync_devices` is idempotent (no duplicate
rows on repeated calls), and the `/api/devices` endpoint returns real probe
results through the full API stack.

Fixed a test regression this phase caused by design: `test_foundation.py`
previously asserted `/api/devices` returns `[]`; that was correct for
Phase 1-9 (no discovery existed) but is no longer the honest behavior now
that real probing runs - split into a datasets-only empty-list test and a
new devices test asserting real (mostly `"not_connected"` in this sandboxed
dev environment, since there's no attached camera/DAQ/microphone) probe
results.

**Verified live**: ran `/api/devices` against the actual dev machine -
correctly reports `thermal_camera`/`vibration_sensor`/`microphone` all
`"not_connected"` with accurate notes (no camera attached here either).

66/66 tests passing (61 previous + 4 new + 1 replaced).

Also added `docs/history/API.md` (endpoint reference) to complete the
documentation set from section 40.

---

## Project status: all 10 phases complete

IDEA LAB now has a working, honestly-instrumented, end-to-end demo:
register a machine → start DEMO MODE with real thermal/vibration/acoustic
dataset sources → watch real per-modality feature extraction stream over
WebSocket → auto-calibrating baselines → layered (statistical + Isolation
Forest) anomaly detection → evidence-level fusion into a health score →
temporal smoothing/hysteresis → persisted history and anomaly events →
charted on a dashboard clearly labelled DEMO MODE → clean stop. The same
`ThermalInput`/`VibrationInput`/`AudioInput` interfaces mean LIVE MODE
needs only real hardware backends behind `LiveThermalCamera`/
`LiveVibrationSensor`/`LiveMicrophone` - no processing-pipeline rewrite.

**Known limitations, stated plainly rather than hidden:**
- Anomaly detection accuracy is modest (Phase 6: ~50% vs ~20% flag rate on
  held-out real bearing acoustic data) - real signal, not production-grade.
  This is expected for a first-pass classical baseline on a genuinely hard
  DCASE-style task, not a bug.
- Live hardware backends (DAQ, microphone capture) are not implemented -
  only the honest "not connected" architecture is, by design, since no
  physical sensors are available yet.
- No automated visual verification of the dashboard charts was possible in
  this environment (no browser); data flow was verified at the API/
  WebSocket level.
- `ToyADMOS-dataset-master/` and the NASA Battery Data Set are present on
  disk but intentionally unused (see `docs/history/DATASETS.md`).
