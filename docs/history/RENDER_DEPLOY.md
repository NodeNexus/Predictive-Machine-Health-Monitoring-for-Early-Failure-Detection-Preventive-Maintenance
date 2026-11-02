# Deploying the IDEA LAB backend to Render

This document covers the **backend only** (a Python FastAPI Web Service —
REST + WebSocket + thermal video streaming). The React/Vite frontend is
deployed separately later; see [Frontend](#frontend) below.

## Service configuration

| Setting | Value |
|---|---|
| Service Type | **Web Service** (not Static Site — this is a dynamic Python server) |
| Runtime | Python |
| Root Directory | repository root (commands below `cd`/prefix into `backend/` themselves) |
| Build Command | `pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 torchvision==0.29.0 && pip install -r backend/requirements.txt` |
| Start Command | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Plan | Free (no paid plan or persistent disk required) |

The actual FastAPI app object is `app` in `backend/app/main.py`. `pytest.ini`
already sets `pythonpath = .` for the `backend/` directory, i.e. `app.main`
is the real importable module path when the process's working directory is
`backend/` — that's exactly what the start command's `cd backend &&` does.

A ready-to-use `render.yaml` Blueprint is committed at the repo root
(backend service only — see [Step 15 scope](#scope) below).

### Build command note (PyTorch)

`backend/requirements.txt` pins `torch==2.14.0` / `torchvision==0.29.0` with
a comment recommending the CPU-only wheel index (Render web services have no
GPU). The build command installs those two packages from
`https://download.pytorch.org/whl/cpu` **first**, then runs the normal
`pip install -r requirements.txt` — pip sees the pinned versions are already
satisfied and does not re-resolve them from PyPI's default (much larger,
CUDA-enabled) wheels. This avoids a slow/oversized build without changing
any pinned dependency version.

### Python version

Pinned via the `PYTHON_VERSION` env var to `3.13.14` — the exact version
already used by this project's own `backend/.venv` and by the full test
suite. No version was previously pinned anywhere in the repo; this value
was **not** guessed, it was read from the working local environment
(`python --version` / `torch.__version__` both checked directly).

## Environment variables

All settings use the existing `IDEALAB_` prefix (`backend/app/core/config.py`,
`pydantic-settings`). Nothing new was invented. See `backend/.env.example`.

| Variable | Required | Purpose |
|---|---|---|
| `IDEALAB_CORS_ORIGINS` | Recommended for production | Comma-separated list of allowed frontend origins, e.g. `http://localhost:5173,https://idealab-frontend.onrender.com`. Plain text, not JSON — see [CORS](#cors) below. Left as `sync: false` in `render.yaml` since the frontend's URL isn't known until it's deployed. |
| `IDEALAB_ENVIRONMENT` | No | Cosmetic — reported by `/api/health`. Set to `production` in `render.yaml`. |
| `IDEALAB_VIDEO_DIR` / `IDEALAB_DATASET_DIR` / `IDEALAB_MODELS_DIR` / `IDEALAB_DB_PATH` | No (only if relocating assets) | Already-existing path overrides — see [Video/model assets](#video-model-assets) below. |

`PORT` is provided by Render itself and consumed directly by the start
command (`--port $PORT`); the app never needs to read it.

## CORS

`backend/app/core/config.py` previously declared `cors_origins` as
`list[str]`. That was changed to a plain `str` (`cors_origins: str`, comma-
separated) with a `cors_origin_list` property doing the split, because
**pydantic-settings JSON-decodes list-typed env values before any validator
runs**, and hard-fails on a plain comma-separated string — confirmed by
actually reproducing the crash locally before fixing it. Render's env var
UI (and most host dashboards) can only enter plain text, so a `list[str]`
field was not actually deployable as-is. `app/main.py`'s `CORSMiddleware`
now reads `settings.cors_origin_list`. `allow_origins=["*"]` is **not**
used — it's also incompatible with the existing `allow_credentials=True`
(browsers reject a wildcard origin on credentialed requests).

## WebSocket

No changes were needed. `GET /ws/telemetry` uses FastAPI's native
`WebSocket` support, which Render's Web Services proxy correctly — Render
terminates TLS and upgrades `wss://` to the backend's plain `ws://`
automatically, standard for any WSGI/ASGI-behind-a-proxy deployment.
Verified locally (see [Local verification](#local-verification)).

The frontend already derives the WebSocket URL from `VITE_API_BASE_URL`
(`ws`→`wss` swap based on the API URL's scheme, see
`frontend/src/services/useTelemetry.ts:telemetryUrl`) — no frontend change
needed for this either.

## Video/model assets

<a id="video-model-assets"></a>

**This is the most important limitation to understand before deploying.**

- ML model weights (`models/thermal/thermal_mobilenetv3_small_v1.pt`,
  `models/vibration/vibration_baseline_v1.joblib`,
  `models/acoustic/acoustic_baseline_v1.joblib`) and the `ml/` training
  package (needed to unpickle/load the thermal model's architecture class)
  **are committed to git** and will be present after a normal Render
  deploy. No action needed.
- The **`VIDEO/` directory (the 7 real machine-mapped `.mp4` files, ~2.2 GB)
  is `.gitignore`d and is NOT part of the repository.** A fresh Render
  deploy will **not** have these files on disk.
- The `DATASET/` directory (IMS vibration + acoustic bearing data, ~16 GB)
  is likewise gitignored and absent.

All model/video/dataset paths are already computed via
`Path(__file__).resolve()` in `backend/app/core/config.py`
(`settings.video_dir`, `settings.dataset_dir`, `settings.models_dir`,
`settings.db_path`) — pure `pathlib`, no Windows-specific separators or
drive letters, confirmed safe on Linux. The three ML model loaders
(`app/pipelines/{thermal,vibration,acoustic}/ml_model.py`) each compute
their own `REPO_ROOT` the same portable way. **No path code needed to
change for Linux/Render compatibility** — the actual blocker is that the
video/dataset *files themselves* aren't shipped with the repository.

**What this means in practice, verified locally:**
- `GET /api/health`, `GET /api/demo/machine-videos`, `GET /docs`, and the
  WebSocket endpoint all work with zero dependency on `VIDEO/`/`DATASET/`
  being present (confirmed).
- `GET /api/datasets` scans `DATASET/`/`VIDEO/` defensively (`.is_dir()`
  checks) and returns an empty list rather than erroring if they're absent.
- Starting a demo session (`POST /api/demo/start`) with a thermal source
  pointing at a missing video **does not crash the server** —
  `ThermalVideoReader.open()` raises `FileNotFoundError`, which
  `demo_runner._thermal_loop` already catches, logs a warning, and returns
  — but that modality simply never produces telemetry.

**To actually stream real thermal video / run a full demo on Render**, the
operator must provide these files at runtime, e.g. by attaching a Render
persistent disk (a **paid** instance feature, deliberately not configured
here per this task's "no paid plan" constraint) and setting
`IDEALAB_VIDEO_DIR` (and `IDEALAB_DATASET_DIR` if vibration/acoustic demo
scenarios are also needed) to that mount path, or by fetching the files
from external object storage during a custom build/start step. This is a
data-provisioning decision for whoever operates the deployment, not a code
defect — flagging it explicitly rather than pretending it deploys itself.

## Machine/video registry

Unchanged. `backend/app/services/demo_scenarios.py`'s `MACHINE_VIDEOS`
remains the single source of truth; `GET /api/demo/machine-videos` still
returns exactly 7 entries. Re-verified locally after this task's changes
(both the automated test suite and a live request against the Render start
command — see below):

```
1.mp4 → Honda Engine
2.mp4 → Honda Engine
3.mp4 → Hydraulic System
4.mp4 → EV Battery
5.mp4 → Transformer
7.mp4 → Engine — With Oil
8.mp4 → Engine — Without Oil
```

`6.mp4` is absent from the registry, the API, and the frontend by
construction — confirmed absent in the live response.

## SQLite persistence

<a id="sqlite"></a>

Unchanged architecture — `backend/app/database/session.py` still uses
`sqlite:///{settings.db_path}`, default `backend/idealab.db` (a plain
`Path`, Linux-safe). This task deliberately did **not** add a persistent
disk or migrate to PostgreSQL (per the "no paid plan" / "don't silently
replace SQLite" constraints).

**Limitation to document, not hide:** Render's free Web Service instances
use ephemeral local disk. Every deploy (and any instance restart/spin-down
on the free plan) gets a fresh filesystem, so the SQLite file — registered
machines, health history, anomaly events, calibrated baselines — **does
not persist** across deploys or restarts on the free plan. This is
acceptable for a demo/prototype deployment; if durable persistence is
needed later, the two supported paths are (a) a paid instance + Render
persistent disk pointed at via `IDEALAB_DB_PATH`, or (b) migrating to a
managed database — neither was done here, by design, since this task's
scope was "prepare and verify," not "add new infrastructure."

## Frontend

<a id="scope"></a>

Out of scope for this task (see instructions §15) — this backend Web
Service does not serve the frontend, and the frontend build was not
changed. `frontend/src/services/api.ts` already reads
`VITE_API_BASE_URL` for the REST base URL, and
`frontend/src/services/useTelemetry.ts` already derives the WebSocket URL
from it (`https` → `wss`, `http` → `ws`), with a same-origin fallback if
unset. No `localhost:8000` is hardcoded anywhere in the frontend source
(verified by search). When the frontend is deployed, set
`VITE_API_BASE_URL=https://<backend-service>.onrender.com` at its build
time, and update the backend's `IDEALAB_CORS_ORIGINS` to include that
frontend's origin.

- **Frontend Production URL:** _to be filled in after the frontend is
  deployed_
- **Backend URL:** _to be filled in after Render creates this service_
- **WebSocket:** `wss://<backend-host>/ws/telemetry`

## How to deploy

1. Push this repository to GitHub/GitLab (already the case).
2. In Render, "New +" → "Blueprint", point it at this repo — it will read
   the committed `render.yaml` and create the `idealab-backend` web
   service. (Or create the Web Service manually using the table above.)
3. Set `IDEALAB_CORS_ORIGINS` once the frontend's URL is known.
4. (Optional, only if you want the real thermal video/dataset demo to
   work) provision `VIDEO/`/`DATASET/` per [Video/model
   assets](#video-model-assets) above and set `IDEALAB_VIDEO_DIR` /
   `IDEALAB_DATASET_DIR` accordingly.

## How to test after deploying

```
curl https://<backend-host>.onrender.com/api/health
curl https://<backend-host>.onrender.com/api/demo/machine-videos
```

Open `https://<backend-host>.onrender.com/docs` for interactive REST docs.
For the WebSocket, connect to `wss://<backend-host>.onrender.com/ws/telemetry`
with any WebSocket client — it will stay open and receive JSON telemetry
envelopes once a demo session is started via `POST /api/demo/start`.

## Local Render-like verification (already performed this session)

Ran the **exact** production start command locally with `PORT=10000`:

```
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 10000
```

Confirmed, against that running instance:
- `GET /api/health` → `200 {"status":"ok","app":"IDEA LAB","environment":"production"}`
- `GET /api/demo/machine-videos` → 7 entries, exact mapping above, no `6.mp4`
- `GET /docs` → `200`
- WebSocket connect to `/ws/telemetry` → succeeds
- `POST /api/demo/start` with a real local `1.mp4` (Honda Engine) →
  `running: true`
- `GET /api/demo/thermal-video` with a `Range` header → `206 Partial
  Content`, `Content-Type: video/mp4`, correct `Content-Range`
- A real telemetry envelope arrived over the WebSocket with a genuine
  computed `thermal.mean_intensity` from the actual video frame (ML
  prediction was `null`/`low` reliability on that specific frame — the
  existing confidence gate behaving correctly, not a deployment issue)
- `POST /api/demo/stop` → `running: false`

This was performed with the real video file present locally — it verifies
the **code path** is Render-compatible end-to-end; it does not verify
Render's actual infrastructure, since the video files are not part of the
deployed repository (see [Video/model assets](#video-model-assets)).
