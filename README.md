# IDEA LAB

Multimodal (thermal + vibration + acoustic) machine-health monitoring and predictive-maintenance platform.

## Status

All 10 build phases complete. A full demo works end-to-end: register a machine, start DEMO MODE against real thermal/vibration/acoustic datasets, watch live per-modality feature extraction and health scoring over WebSocket telemetry, with auto-calibrating baselines, layered anomaly detection, evidence-level fusion, temporal smoothing, and a charted dashboard. See `docs/ARCHITECTURE.md` for the system design, `docs/API.md` for the endpoint reference, `docs/DATASETS.md` for what's actually in the downloaded datasets, and `docs/DEVELOPMENT.md` for the full phase-by-phase history (including known limitations, stated plainly).

Quick start once both servers are running (see below): open the dashboard, use the **Demo Mode** panel to pick a machine and enter dataset paths (e.g. a thermal MP4 from `VIDEO/`, an IMS test directory + channel from `DATASET/IMS/IMS/1st_test/1st_test`, a WAV from `DATASET/bearing/bearing/train/`), and press Start.

## Project layout

```
backend/    FastAPI application (API, WebSocket telemetry, pipelines, fusion, database)
frontend/   React + TypeScript + Vite dashboard
data/       Derived/processed data and manifests (raw datasets are NOT committed)
DATASET/    Downloaded raw datasets (gitignored — development/validation material only)
VIDEO/      Downloaded thermal demo videos (gitignored)
docs/       Architecture and development documentation
scripts/    Standalone tooling (dataset inspection, etc.)
```

## One-click startup

The fastest way to run IDEA LAB on Windows, once the backend virtual environment and frontend `node_modules` already exist (see **Running locally** below for first-time setup):

1. Double-click **`run_idea_lab.bat`** in the project root.
2. A console window walks through project/environment checks, runs the dataset scanner, then opens two more windows titled **"IDEA LAB - BACKEND"** and **"IDEA LAB - FRONTEND"** — leave those open; they show live server logs.
3. Your default browser opens automatically once both servers respond.
4. If it doesn't open automatically, go to: **http://localhost:5173**

Closing the original launcher window does **not** stop the backend or frontend — they keep running in their own windows. To stop IDEA LAB, close those two windows directly (or press Ctrl+C inside them).

The launcher will not silently create a virtual environment or run `npm install` for you — if either is missing, it prints the exact command to run and exits. It also won't create fake "connected" state or force-kill unrelated processes: if port 8000 or 5173 is already in use, it warns and continues rather than guessing.

## Running locally

To start each server manually (e.g. on first-time setup, or on macOS/Linux, or to run backend/frontend independently):

Backend:

```
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` and `/ws/*` to `http://127.0.0.1:8000`.

## Tests

```
cd backend
./.venv/Scripts/python.exe -m pytest tests/ -v
```
