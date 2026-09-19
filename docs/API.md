# API Reference

All endpoints are served by the FastAPI backend (`backend/app/main.py`). Base URL in development: `http://127.0.0.1:8000` (or via the Vite proxy at `http://localhost:5173/api/...`).

## Health

`GET /api/health` → `{status, app, environment}`

## Machines

- `GET /api/machines` — list all registered machines
- `POST /api/machines` — create a machine (`machine_name` required; type/manufacturer/model/rpm/rated_power/location/sensor_configuration optional)
- `GET /api/machines/{id}` — get one machine
- `GET /api/machines/{id}/status` — current `MachineHealthState` (from the latest `HealthHistory` row, or an honest `"unknown"` state with `missing_modalities` if nothing has run yet)
- `GET /api/machines/{id}/history?limit=200` — recent health-score/status points
- `GET /api/machines/{id}/events?limit=50` — anomaly events (start/resolve times, severity, modality contributions, evidence)

## Datasets

`GET /api/datasets` — the dataset registry, populated by `scripts/scan_datasets.py`. Empty until that scanner has run.

## Devices

`GET /api/devices` — runs a real hardware probe on every call (thermal camera via OpenCV `VideoCapture` index enumeration; vibration/microphone honestly report `"not_connected"` since no DAQ/audio-capture backend is integrated yet) and returns the current state. Never fabricates a `"connected"` device.

## Demo Mode

- `POST /api/demo/start` — body: `{machine_id, thermal_source?, vibration_source?, vibration_channel?, acoustic_source?, playback_speed?}`. Source paths are absolute filesystem paths (an MP4 for thermal, an IMS-style test directory for vibration, a WAV file for acoustic). Starts per-modality asyncio processing loops + the fusion/broadcast loop. Returns `409` if a session is already running.
- `POST /api/demo/stop` — stops all loops, closes readers, ends the `MonitoringSession`.
- `GET /api/demo/status` — `{running, machine_id, session_id, sources, started_at}`.

## Realtime telemetry

`WS /ws/telemetry` — broadcasts a `TelemetryPayload` roughly every second while a demo (or, eventually, live) session is running:

```json
{
  "timestamp": "...",
  "machine_id": "...",
  "mode": "demo",
  "thermal": { "source": "...", "mean_intensity": ..., "hotspot_area_fraction": ..., ... } | null,
  "vibration": { "source": "...", "rms": ..., "band_energies": {...}, "spectral_peaks": [...], ... } | null,
  "acoustic": { "source": "...", "rms": ..., "mfcc": [...], "band_energies": {...}, ... } | null,
  "health": { "health_score": ..., "status": "...", "confidence": ..., "evidence": [...] },
  "events": [{"type": "event_started" | "event_cleared", ...}]
}
```

Each modality block is the full feature model from that modality's analyzer (see `docs/ARCHITECTURE.md`), not a cut-down summary — the dashboard's charts (octave bands, spectral peaks, MFCCs) read directly from this payload.
