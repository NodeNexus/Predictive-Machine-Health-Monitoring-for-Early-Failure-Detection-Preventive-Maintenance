# Architecture

## Principle

DEMO MODE and LIVE MODE share identical downstream processing. Only the
input adapter differs:

```
Demo:  Thermal MP4  -> frame reader     -> ThermalInput -> thermal analyzer
Live:  Thermal cam   -> camera adapter  -> ThermalInput -> thermal analyzer
```

The same holds for vibration (`VibrationInput`) and acoustic (`AudioInput`).
These abstractions live in `backend/app/pipelines/common/interfaces.py`.

## Pipeline shape

```
Input Manager
   |
   +-- Thermal Adapter   -> Thermal Frames    -> Thermal Analyzer   -> Thermal Evidence
   +-- Vibration Adapter -> Signal Windows    -> Vibration Analyzer -> Vibration Evidence
   +-- Acoustic Adapter  -> Audio Windows     -> Acoustic Analyzer  -> Acoustic Evidence
                                                        |
                                                  Fusion Engine
                                                        |
                                          Health Score / Anomaly Level / Evidence
                                                        |
                                                  Event Engine
                                                        |
                                    Dashboard (WebSocket) / Alerts / Reports
```

Fusion is evidence/score-level, not raw concatenation — the currently
available datasets are not guaranteed to be synchronized recordings of the
same physical machine, so modality-specific analysis happens first and only
the resulting evidence is fused.

## Streaming model

Processing is window-oriented, not full-file:

- Thermal: `read_frame()` one frame at a time.
- Vibration / Acoustic: samples are pushed into a `SlidingWindowBuffer`
  (configurable window size + hop), which emits fixed-size windows as they
  become available — the same buffer class is used for both modalities and
  for demo playback and live streaming alike.

## Backend layout

```
backend/app/
  core/        settings (all tunable parameters), structured logging
  database/    SQLAlchemy models + session (SQLite)
  pipelines/
    common/    ThermalInput / VibrationInput / AudioInput interfaces, SlidingWindowBuffer
    thermal/   (Phase 3)
    vibration/ (Phase 4)
    acoustic/  (Phase 5)
  fusion/      (Phase 7)
  devices/     device discovery / hardware abstraction (Phase 10)
  datasets/    dataset scanning / manifest generation (Phase 2)
  services/    demo_runner (session lifecycle), telemetry_hub (WebSocket broadcast)
  api/         REST routes + WebSocket endpoint
  models/      Pydantic schemas shared by REST + WebSocket payloads
  main.py      FastAPI app assembly
```

## Honesty rule

No component may fabricate a diagnostic value. Where a subsystem does not
yet have real processing behind it (e.g. dataset registry before Phase 2
scanning has run), it returns an honestly empty/unknown state rather than
placeholder data.
