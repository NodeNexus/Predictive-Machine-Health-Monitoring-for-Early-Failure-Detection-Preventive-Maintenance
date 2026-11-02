# Multimodal Machine Health Monitoring and Anomaly Detection — Project Guide

**This is the main guide.** It replaces the top-level README's detail and the separate API, architecture and dataset notes. Phase-by-phase history and the detailed thermal audit and split reports are kept, unchanged, in [`docs/history/`](history/) and are linked where relevant.

> **Scope in one sentence:** Multimodal Machine Health Monitoring and Anomaly Detection is a research prototype that streams recorded thermal, vibration and acoustic data through a feature pipeline, scores machine health with transparent baselines and layered anomaly checks, and shows the result on a live dashboard. It is **not** a validated fault diagnosis or remaining-useful-life product.

---

## 1. Purpose and status

- Multimodal machine-health monitoring: **thermal** (video/images), **vibration** (IMS bearing run-to-failure) and **acoustic** (machine-sound WAVs). The backend has an evidence-level fusion engine (§6.4), but the dashboard shows each signal's result **separately**: the recordings come from different machines and are not synchronised, so a combined diagnosis would not be honest.
- Working end to end in **DEMO MODE**: register a machine, point the demo at real dataset files, watch per-modality features, health scores and events over WebSocket telemetry.
- All 10 build phases are marked complete in [`history/DEVELOPMENT.md`](history/DEVELOPMENT.md). Phase summary:

| Phase | Area |
|---|---|
| 0–1 | Environment check; FastAPI + React foundation, database, WebSocket |
| 2 | Dataset inspection and registry scan |
| 3–5 | Thermal, vibration and acoustic feature engines |
| 6 | Baseline calibration and layered anomaly detection |
| 7 | Evidence-level fusion and temporal smoothing |
| 8–9 | Demo Mode lifecycle and charted dashboard |
| 10 | Live input adapters and honest device discovery (no fabricated "connected" states) |

## 2. Honesty rules (apply everywhere)

- **No fabricated values.** If a modality or baseline is missing, the API says so (`unknown`, `missing_modalities`, `not_connected`). Nothing is filled in with placeholders.
- **Derived labels are not ground truth.** The IMS dataset has no per-file health labels; the vibration ML labels are produced by a documented rule (see §6.2).
- **Demo ≠ validation.** A demo run shows the engine working on real files, not that it is accurate for deployment.
- **Thermal class meanings are not verified** from dataset documentation (see §6.3).

## 3. Scope and limitations

**In scope:** feature extraction, baselines, anomaly flags, evidence fusion, replaying recorded data, and a dashboard for inspecting results.

**Out of scope or not yet built:**
- Live hardware: the vibration DAQ and microphone adapters report `not_connected`; live thermal camera capture is probed but not wired into the demo loop.
- Remaining-useful-life estimation, fault-type identification, or any claim of validated diagnosis.
- Deep anomaly models: "Level 3" in the layered detector is deliberately not implemented ([`history/DEVELOPMENT.md`](history/DEVELOPMENT.md), Phase 6).
- Production deployment and authentication. The demo is hosted on a Raspberry Pi behind a Cloudflare Quick Tunnel, optionally behind a stable Render URL (§8.1). Anyone with either link can use the dashboard. The older backend-only Render notes for the root `render.yaml` are in [`history/RENDER_DEPLOY.md`](history/RENDER_DEPLOY.md).

## 4. Datasets and attribution

**Raw data is not part of this project's distribution.** The `DATASET/` and `VIDEO/` folders are local, gitignored copies used for development and validation. See §10 for a known problem with files already tracked in git.

| Data used | What it is | Source (as recorded in this repo) | Licence / terms | Redistribution |
|---|---|---|---|---|
| IMS bearing run-to-failure (`DATASET/IMS/IMS/{1st,2nd,3rd}_test`) | 4 bearings on a shaft, 2000 RPM, 6000 lb radial load, 20 kHz, 20,480-point ASCII snapshots, 8/4/4 channels | Vendor readme in the dataset folder: NSF I/UCR Center for Intelligent Maintenance Systems with Rexnord Corp. Reference: Qiu, Lee, Lin, *J. Sound and Vibration* 289 (2006) 1066–1090. | **Not stated in the readme. Verify the terms at the NASA Prognostics Data Repository before any redistribution.** | Do not redistribute raw files. |
| Machine sound, DCASE-style (`bearing`, `fan`, `valve`, `gearbox`) and MIMII-style (`dev_data_pump`) | 16 kHz mono WAV, ~10 s clips, normal-only training subsets | Recorded in [`history/DATASETS.md`](history/DATASETS.md). Described in the development log as MIMII / DCASE Task 2-style. | **Not recorded in the repo. Verify the source and licence before use or redistribution.** | Do not redistribute. |
| ToyADMOS (`DATASET/ToyADMOS-dataset-master/`) | Repository scripts and documentation only; contains **no audio** | ToyADMOS by NTT Media Intelligence Laboratories (Koizumi et al.); the audio is on Zenodo (record 3351307). | **NTT software evaluation licence (`LICENSE.pdf`):** internal evaluation use only; no copying, distribution or disclosure to third parties. | Do not redistribute. Not used by the app. |
| NASA Battery Data Set (`DATASET/5. Battery Data Set/`) | Battery ageing data | NASA | Not recorded | Not used; excluded from the scanner. |
| Induction-motor thermal images (`_thermal_audit_ds1/`, `_thermal_audit_ds2/`) | Dataset 1: 488 thermal JPEGs (6 classes). Dataset 2: BMP images with paired TIFF masks (369 records in its split manifest) | Mendeley Data, DOIs `pymtdhfzbj` (dataset 1) and `m4sbt8hbvk` (dataset 2), per [`history/THERMAL_DATASET_AUDIT.md`](history/THERMAL_DATASET_AUDIT.md) | **Not recorded in the repo. Verify on Mendeley Data before use or redistribution.** | Do not redistribute. |
| Thermal demo videos (`VIDEO/*.mp4`, 8 files) | Recordings of a thermal camera's display (not radiometric) | Source not recorded in the repo | **Unknown** | Do not redistribute. |

**Attribution rule for any publication or demo:** cite the dataset source above, state the licence you verified, and do not describe derived labels as original dataset ground truth.

## 5. Inputs and outputs

### 5.1 Inputs

| Modality | Input | Notes |
|---|---|---|
| Thermal | MP4 video (demo) or thermal images | Read frame by frame. Thermal ML classifies images from the Dataset 1 test split. |
| Vibration | IMS test directory (tab-separated ASCII snapshots) and a channel index (0-based) | 20 kHz, 20,480 samples per file. |
| Acoustic | WAV files (16 kHz, mono) | Demo replays a file; live capture is not implemented. |
| Machine | `POST /api/machines` with `machine_name` and optional metadata | |

### 5.2 Outputs

- **Per-modality features** (for example RMS, kurtosis, crest factor, octave bands, MFCCs) and evidence (`evidence` list).
- **Health state** (`GET /api/machines/{id}/status`): `health_score`, `status`, `confidence`, `missing_modalities`.
- **Anomaly events** (`GET /api/machines/{id}/events`): start and resolve times, severity, modality contributions.
- **Live telemetry** (`WS /ws/telemetry`, about once per second while a demo runs). Payload shape: `timestamp`, `machine_id`, `mode`, `thermal`, `vibration`, `acoustic` (each `null` if absent), `health`, `ml_fusion`, `events`, and `progress` (per running modality: `unit` of `seconds` or `files`, `position`, `total`, `loop`; absent if unknown).
- **ML evidence** for thermal, vibration and acoustic, with model version and class probabilities.

## 6. Models and evaluation

### 6.1 Anomaly engine (all modalities)

Two layers: statistical z-scores against a calibrated per-machine baseline, and an Isolation Forest, fitted when a baseline exists. A window is flagged `anomalous` if **either** layer flags it, which favours recall for maintenance alerts. The engine returns `unknown` until a baseline exists.

**Measured result (acoustic `bearing`, 150 normal training files as baseline):** 60 held-out normal files, 12 flagged (20%); 60 anomaly files, 30 flagged (50%). This shows real separation but is **not production-ready**. See [`history/DEVELOPMENT.md`](history/DEVELOPMENT.md), Phase 6.

### 6.2 Vibration ML (`models/vibration/`)

- **Task:** three derived classes, `healthy` / `degrading` / `severe`, on IMS 1st_test channel 4 (bearing 3).
- **Labels are derived, not ground truth.** Baseline = files 0–99. A file is `healthy` if z(RMS) < 3; `severe` if z(kurtosis) ≥ 10; otherwise `degrading`. Resulting counts: 155 / 1,678 / 323.
- **Split:** 2,156 files in contiguous 20-file blocks, stratified by each block's dominant label, then split 70/15/15 chronologically within each stratum. Train 1,500, validation 320, test 336. Residual adjacency risk at stratum boundaries is documented in `models/vibration/vibration_task_definition.json`.
- **Model selection:** on validation macro-F1, Logistic Regression 0.988, Random Forest 1.0, Gradient Boosting 1.0. The selected model is the Random Forest (ties resolved by the script's order).
- **Test macro-F1 1.0 is circular.** RMS and kurtosis are both label-defining and model inputs. Ablations in `models/vibration/model_metadata.json`: without RMS and kurtosis, 0.968; spectral and skewness only, 0.857. **Read the 1.0 only with this caveat;** the 0.857 figure is the closer estimate of independent signal.
- The dashboard shows this limitation on the Analytics page.

### 6.3 Thermal ML (`models/thermal/`)

- MobileNetV3-Small, ImageNet-pretrained, fine-tuned (last two blocks and head) on Dataset 1, 6 classes: `HFL`, `HML`, `HNL` (healthy at full, medium, no load) and `CFL`, `CML`, `CNL` (the `C` group at the same loads).
- **Test results** (`models/thermal/test_evaluation.json`): accuracy 0.725, macro-F1 0.580, top-3 accuracy 0.961. Some classes score 0 F1 (for example `CFL`). A confidence gate (`backend/app/pipelines/thermal/confidence_gate.py`) controls how predictions are displayed.
- **Split:** leak-proof by image hash, with group-aware checks; see [`history/THERMAL_SPLIT_REPORT.md`](history/THERMAL_SPLIT_REPORT.md).
- **The meaning of `C` ("Corroded Bearing") is not verified.** The audit found no local documentation for it. The label came from the project brief. Treat the fault name as unverified until the dataset's source paper is checked (see §10).
- Requires PyTorch, which is optional (§7.2). Without it the thermal ML is reported as unavailable.

### 6.4 Fusion and temporal smoothing

Fusion works on evidence, not raw concatenation, because the datasets are not synchronised recordings of one machine. Modalities that are not streaming are listed in `missing_modalities`. Temporal smoothing is applied to the fused score. Details: [`history/ARCHITECTURE.md`](history/ARCHITECTURE.md), [`history/DEVELOPMENT.md`](history/DEVELOPMENT.md) Phase 7.

### 6.5 Acoustic ML (`models/acoustic/`)

- **Task:** `normal` / `anomaly` on the DCASE-style bearing sound dataset (`DATASET/bearing/bearing`). These labels are the **dataset's own**, not derived by this project.
- **Model:** logistic regression (`acoustic-v1`), class-weighted for the roughly 11:1 normal-to-anomaly ratio. It was selected on validation macro-F1: logistic regression 0.886, gradient boosting 0.884, random forest 0.859. Splits are 2,519 train, 543 validation and 537 test clips.
- **Test results** (`models/acoustic/test_evaluation.json`):
  - 41 of 42 anomaly clips caught (recall 0.976).
  - 21 of 495 normal clips falsely flagged (normal recall 0.958, anomaly precision 0.66).
  - Macro-F1 0.883, ROC-AUC 0.991.
- **Domain shift:** accuracy drops on the dataset's "target" domain, for example 0.81 on section 00 against 0.99 on its source domain (`robustness_by_section_domain_group` in the same file).
- The demo replays one normal clip from the bearing **training** split (`acoustic_bearing_normal` in `backend/app/services/demo_scenarios.py`). The model has seen that clip, so its result in the demo shows the pipeline working, not test accuracy.

## 7. Setup and running (Windows)

### 7.1 Prerequisites

- Python 3.12 (the backend venv was built with 3.12.14; the older dev log mentions 3.13 — either works, use one consistently).
- Node.js with npm on `PATH`.
- Optional: 7-Zip, to extract the `.rar` and `.7z` archives in `DATASET/`.

### 7.2 Backend environment (one time)

Run these from the project root in PowerShell or Command Prompt:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Use `python -m pip`, not a bare `pip`: on Windows the `pip` launcher can point at a different Python. PyTorch is optional. For the thermal model, install a CPU build from the PyTorch index instead of PyPI, which pulls GPU dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
```

### 7.3 Frontend (one time)

```powershell
cd frontend
npm install
```

### 7.4 Run the app

**One-click (recommended):** double-click `start_all.bat` in the project root. It:
- creates the backend venv and installs the backend packages if they are missing
- checks the frontend packages
- starts the backend (port 8000) and frontend (port 5173) in their own windows, reusing servers that are already running
- opens <http://localhost:5173>

`run_idea_lab.bat` is the older launcher. It needs the venv and `npm install` done beforehand, and it also runs the dataset scanner (§7.5) on every start.

**Manually, two terminals:**

```powershell
# Terminal 1 — backend
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

The Vite dev server proxies `/api/*` and `/ws/*` to `http://127.0.0.1:8000`. Open <http://localhost:5173>.

### 7.5 Refresh the dataset registry

```powershell
cd backend
.\.venv\Scripts\python.exe ..\scripts\scan_datasets.py
```

This writes `data/manifests/dataset_manifest.json` and upserts the `DatasetRegistry` table in `backend/idealab.db`. The launcher runs it on every start, which also refreshes stored paths.

### 7.6 Run the tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

The first run can take a few minutes (the vibration and dataset tests read real files). Tests skip gracefully when optional data or torch is absent.

### 7.7 Common Windows errors

| Symptom | Cause and fix |
|---|---|
| `Fatal error in launcher: Unable to create process using ...pip.exe` | The `pip` launcher points at a Python that no longer exists. Never call `pip` directly: use `.\.venv\Scripts\python.exe -m pip ...` from `backend`. |
| `pip install -r requirements.txt` finds no file | There is no `requirements.txt` in the project root. It is `backend\requirements.txt` (`requirements-dev.txt` for tests). |
| `no tests ran ... file or directory not found: tests/` | Run pytest from `backend`, or use `backend\.venv\Scripts\python.exe -m pytest backend/tests`. |
| `npm was not found on PATH` | Install Node.js from nodejs.org. `run_idea_lab.bat` now falls back to `node node_modules\vite\bin\vite.js` when only `node` is present and `frontend\node_modules` exists. |
| `GET / 404 Not Found` and `/favicon.ico 404` in the backend terminal | Expected. The backend is API-only (`/api/...`, docs at `/docs`). The dashboard is the frontend at http://localhost:5173. |
| Dashboard says "Backend unreachable" while a replay is starting | Fixed. Loading the thermal model (PyTorch) used to run on the backend's event loop and froze every API call and the WebSocket for 10-20 seconds on the first replay after a backend start. It now loads in a worker thread. If you still see it, the banner states the real cause: connection refused, no answer in time, a proxy 502, or another program answering on port 8000. |
| `[Errno 10048] ... only one usage of each socket address` | Port 8000 is already held. With `--reload`, closing the terminal window can leave the reload worker running (it keeps answering, with old code). Find it with `netstat -ano \| findstr :8000` and end it with `taskkill /PID <pid> /F`. `start_all.bat` detects this and names the process. |
| `http://127.0.0.1:5173` refused to connect | Vite used to listen on IPv6 `localhost` only. `frontend/vite.config.ts` now binds `127.0.0.1`, so both `http://127.0.0.1:5173` and `http://localhost:5173` work. |
| `python src/pm/serve.py` cannot find the file | That belongs to the separate `MECHANICAL_PREDICTIVE_MAINTENANCE` project, not this one. |

### 7.8 Verify the install

- `GET http://127.0.0.1:8000/api/health` returns `{"status": "ok", "app": "Multimodal Machine Health Monitoring and Anomaly Detection", ...}`.
- The dashboard shows the device status and dataset registry summary.

## 8. Dashboard usage

One page in `frontend/src/components/dashboard/` (the earlier multi-page shell was removed and remains in Git history, commit `f4bd0ee9`). The typeface is Bahnschrift, a DIN-style industrial face that ships with Windows 10+, with Roboto/Segoe UI fallbacks. A **DEMO MODE** badge marks that prerecorded files are replayed through the backend; nothing is read from live sensors.

- **Input:** choose a machine video, and optionally a vibration run and a sound clip, then **Start test** / **Stop**. Options come from `GET /api/demo/machine-videos` and `GET /api/demo/scenarios`.
- **Test window:** the selected video plays from the click, with playback progress and elapsed time. A second line per input shows the backend's own analysis position (the backend decodes the file separately from the browser player, so the two positions differ).
- **Output:** per input, the model result, confidence and reliability, model version and last-update time, all from telemetry. Thermal also shows frame brightness mean/max and hotspot area. Status and events are shown only when a single input is selected. There is no combined result: the recordings are not verified as aligned.
- **Model test results:** accuracy, macro-F1 and top-3 accuracy from `GET /api/demo/thermal-evaluation` (the saved `models/thermal/test_evaluation.json`: 72.5 %, 0.580, 96.1 % on 51 held-out still images), plus one held-out example per class from `GET /api/demo/thermal-image-feed` with its known label and the model's prediction. Accuracy on the demo videos has not been measured.

Behaviour worth knowing:
- **Video:** `GET /api/demo/thermal-video` streams the active session's video with HTTP Range support, and only for catalogued videos (others get 403).
- **Telemetry socket:** it exists only while a test runs. Stop closes it, releases the video and clears the Output.
- **Best guess:** below the 0.6 reliability threshold the backend withholds the thermal class (`ml_prediction` stays null) but now also sends the model's raw top class as `ml_top_class`. The page shows it as a tentative "best guess, low confidence" with the real confidence; the threshold is unchanged.
- **Heat intensity:** the thermal videos are camera-display recordings with no calibrated temperature data, so the page shows relative image brightness (0-255), never degrees.
- **Thermal results:** the classifier was trained on induction-motor still images. On the demo clips it often returns no confident class; when it does return one, treat it as unvalidated.
- **Machines:** Start reuses one machine per distinct choice of runs and creates it only the first time.
- **Honest state:** the header shows backend reachability and the feed state separately. Backend failures, a dropped feed, missing data and video load errors are stated as such.
- **Start validation:** `POST /api/demo/start` returns 400 when no source is given and 422 when a source cannot be replayed.

Run it with the backend (`python -m uvicorn app.main:app --port 8000` in `backend`) and `npm run dev` in `frontend`.

### 8.1 Hosting the demo: Raspberry Pi, Quick Tunnel and Render

```
browser ──► https://<service>.onrender.com ──► https://<random>.trycloudflare.com ──► Pi backend + dashboard (127.0.0.1)
            (stable, optional)                 (changes on every restart)
```

- **Pi** ([`PI_DEMO.md`](PI_DEMO.md)): the backend serves the built dashboard itself, on one local port. `start.sh`, `status.sh` and `stop.sh` touch only this project's processes on the shared Pi.
- **Quick Tunnel:** `start.sh` opens one and prints its public URL. The URL changes on every start.
- **Render gateway** ([`RENDER_GATEWAY.md`](RENDER_GATEWAY.md)): a small Node proxy on Render's free tier gives the demo one fixed URL. It forwards pages, API calls, video and the telemetry WebSocket to the current tunnel.
  - The Pi registers each new tunnel URL with a shared token, and only `*.trycloudflare.com` targets are accepted.
  - While the Pi is offline, the gateway shows an "offline" page.
  - The free instance sleeps after 15 minutes idle, so the first visit after that takes about a minute.
- **No authentication on either URL.** Anyone with the link can press Start/Stop. Stop the demo after presenting.

## 9. API reference (summary)

Full endpoint details are in [`history/API.md`](history/API.md). Base URL `http://127.0.0.1:8000`.

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Liveness: `{status, app, environment}` |
| `GET, POST /api/machines` | List and create machines (`machine_name` required) |
| `GET /api/machines/{id}` | One machine |
| `GET /api/machines/{id}/status` | Current health state, or `unknown` with `missing_modalities` |
| `GET /api/machines/{id}/history?limit=200` | Recent health-score points |
| `GET /api/machines/{id}/events?limit=50` | Anomaly events |
| `GET /api/datasets` | Dataset registry rows (empty until a scan has run) |
| `GET /api/devices` | Live device probe |
| `GET /api/demo/thermal-evaluation` | Saved held-out test-image metrics of the thermal classifier (read-only) |
| `GET /api/demo/thermal-image-feed`, `/{image_id}` | Held-out test images with known label (`true_class`) and the model's prediction |
| `GET /api/demo/thermal-video` | Active session's thermal video (Range supported; catalogued videos only) |
| `POST /api/demo/start` | Body: `machine_id`, plus `thermal_source`, `vibration_source`, `vibration_channel`, `vibration_start_file`/`vibration_end_file`, `acoustic_source`, `playback_speed`. Source paths are absolute. `400` if no source is given, `422` if a source cannot be replayed, `409` if a session is running. |
| `POST /api/demo/stop` | Stop the session |
| `GET /api/demo/status` | `{running, machine_id, session_id, sources, started_at}` |
| `WS /ws/telemetry` | Telemetry stream during a session |

## 10. Known issues

1. **Raw datasets are in a local, unpushed commit.** Commit `f4bd0ee9` ("Add complete datasets and video assets via Git LFS") tracks 28,162 files under `DATASET/` and `VIDEO/`. It exists only on this PC: GitHub's `main` is still `c73e8412`, which contains no `DATASET/` or `VIDEO/` files. **Do not push local `main` as it is.** Pushing it uploads every dataset and video through Git LFS. Some of those files are under terms that forbid redistribution (ToyADMOS, §4). A push started on 2026-10-31 was stopped before any branch was created, but some LFS objects may already have been uploaded to GitHub's LFS storage. **Recommended fix:** untrack the data with `git rm -r --cached DATASET VIDEO` before the next commit on `main`. Whether to drop `f4bd0ee9` itself is a separate decision, so it has not been done. The `render-gateway` branch on GitHub is built directly on `c73e8412` and carries only `deploy/`.
2. **Git ownership warning.** Git refuses this repo with "dubious ownership" because the folder is owned by a different SID. Run git with `git -c safe.directory=D:/TASKS/MECHANICAL ...` or fix ownership. The global config was not changed.
3. **Stale absolute paths.** The committed manifests (`data/manifests/*.json`) and the registry rows still record paths under `C:\Users\VNAV-PC\Desktop\MECHANICAL\`. The code now re-roots such paths onto the checkout when reading them (`backend/app/core/paths.py`, `ml/thermal/dataset.py`), so tests and the feed pass. The manifest files themselves were not rewritten.
4. **Vibration ML label circularity** (§6.2). The 1.0 test F1 is not evidence of independent fault detection.
5. **Thermal class meaning unverified** (§6.3), and the model is modest (macro-F1 0.58).
6. **Acoustic anomaly false positives** near 20% (§6.1).
7. **Model metadata references an old path.** `models/vibration/vibration_task_definition.json` names `docs/THERMAL_SPLIT_REPORT.md`, now at `docs/history/THERMAL_SPLIT_REPORT.md`. Model artifacts were not edited.
8. **Dataset licences are not recorded** for the acoustic, thermal and video sources (§4).
9. **Test count drift.** The older docs in `history/` cite "5" or "46" tests from earlier phases. The current suite has 199 tests, all passing on 2026-10-31 (about 100 s). The suite itself (`pytest tests/ -v`) is the source of truth.

## 11. Project layout

```
backend/        FastAPI app (API, WebSocket, pipelines, fusion, database), tests, requirements
  app/core/paths.py        re-roots stale absolute paths onto this checkout
frontend/       React + TypeScript + Vite dashboard (see docs/FRONTEND.md)
ml/             training and inference code: thermal, vibration, acoustic
models/         trained artifacts and their metadata (do not edit by hand)
data/           manifests (small JSON) and processed feature tables
DATASET/        raw local datasets (gitignored; see §4 and §10)
VIDEO/          thermal demo videos (gitignored; see §4)
_thermal_audit_ds*/  extracted induction-motor thermal datasets used by the thermal model
scripts/        dataset scanning, split preparation, evaluation and demo scripts
deploy/pi/      Raspberry Pi demo scripts (start, stop, status, Render sync)
deploy/render/  Render gateway: stable URL that forwards to the Pi's Quick Tunnel
docs/           all documentation: this guide, FRONTEND.md, PI_DEMO.md, RENDER_GATEWAY.md;
                docs/history/ holds the phase log, API, architecture, dataset and
                thermal audit documents, the old Render notes, the research report, the dataset
                listing and the frontend design notes
submission/     Seva Innovation Challenge 2026 deck (.pptx, .pdf), its template, team document
start_all.bat     one-click Windows setup and launcher (recommended)
run_idea_lab.bat  older launcher (needs setup done first)
render.yaml       backend-only Render blueprint (see history/RENDER_DEPLOY.md)
```

## 12. Related documents

- [`history/DEVELOPMENT.md`](history/DEVELOPMENT.md): phase-by-phase decisions, findings and test history.
- [`history/ARCHITECTURE.md`](history/ARCHITECTURE.md): pipeline and streaming design; the honesty rule.
- [`history/API.md`](history/API.md): full endpoint and telemetry payload reference.
- [`history/DATASETS.md`](history/DATASETS.md): what the scanner found in each dataset.
- [`history/THERMAL_DATASET_AUDIT.md`](history/THERMAL_DATASET_AUDIT.md) and [`history/THERMAL_SPLIT_REPORT.md`](history/THERMAL_SPLIT_REPORT.md): thermal dataset audit and leak-proof split.
- [`FRONTEND.md`](FRONTEND.md): dashboard code layout, commands and build settings.
- [`PI_DEMO.md`](PI_DEMO.md) and [`RENDER_GATEWAY.md`](RENDER_GATEWAY.md): hosting the demo (§8.1).
- [`history/RENDER_DEPLOY.md`](history/RENDER_DEPLOY.md): older backend-only Render deployment notes for the root `render.yaml`.
- [`history/deep-research-report.md`](history/deep-research-report.md): background research report.
- [`history/dataset_structure.txt`](history/dataset_structure.txt): directory listing of the raw datasets.
- [`history/frontend-design/`](history/frontend-design/): design notes and screenshots from the first dashboard; the current dashboard replaced it.
