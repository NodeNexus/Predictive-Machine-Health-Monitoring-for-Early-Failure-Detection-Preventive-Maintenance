# Multimodal Machine Health Monitoring and Anomaly Detection

Research prototype for monitoring machine health from **thermal video, vibration and sound**. It replays real recorded
datasets through feature extraction, baselines, anomaly checks and trained models, and shows each signal's result on
a single-page dashboard. Each signal is judged separately: the recordings are not synchronised, so there is no
combined diagnosis. It is **not** a validated fault-diagnosis or remaining-useful-life product.

**Main guide: [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md).** It covers:
- scope and limitations
- dataset sources and licences
- inputs and outputs
- models and their measured results
- setup and dashboard use
- hosting
- known issues

## Measured results (held-out test data)

| Signal | Model | Result |
|---|---|---|
| Sound | logistic regression, normal / anomaly (bearing sounds, the dataset's own labels) | 41 of 42 faulty clips caught (98%), 21 of 495 normal clips falsely flagged, macro-F1 0.88 |
| Thermal | MobileNetV3-Small, 6 classes | 72.5% accuracy, 96.1% top-3, on 51 still images; accuracy on the demo videos has not been measured |
| Vibration | Random Forest, 3 derived classes | test macro-F1 1.0 is circular (labels come from the same features); 0.857 without them. See the guide, §6.2 |

## Run on Windows

Double-click **`start_all.bat`**. It sets up the backend venv if needed, starts the backend (port 8000) and
frontend (port 5173), and opens <http://localhost:5173>.

To run them by hand:

```
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

cd frontend
npm run dev        # open http://localhost:5173
```

To run the tests (199 tests, about 2 minutes):

```
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

## Demo hosting

- **Raspberry Pi:** the backend serves the dashboard behind a Cloudflare Quick Tunnel. See [docs/PI_DEMO.md](docs/PI_DEMO.md).
- **Stable URL (optional):** a Render gateway gives the demo one fixed address and follows the tunnel. See [docs/RENDER_GATEWAY.md](docs/RENDER_GATEWAY.md).
- **No authentication:** anyone with either link can use the dashboard. Stop the demo after presenting.

## Folders

| Folder | Contents |
|---|---|
| `backend/` | FastAPI app, pipelines, tests |
| `frontend/` | React dashboard ([docs/FRONTEND.md](docs/FRONTEND.md)) |
| `ml/` | training and inference code |
| `models/` | trained models |
| `data/` | manifests and processed features |
| `scripts/` | dataset, training and evaluation scripts |
| `deploy/` | Pi and Render hosting |
| `docs/` | all documentation: the guide, frontend, Pi demo and Render gateway docs, plus history and audits in `docs/history/` |
| `submission/` | Seva Innovation Challenge 2026 deck and team document |

Raw datasets (`DATASET/`, `VIDEO/`, `_thermal_audit_ds*/`) are local copies with their own licences. Do not
redistribute them; see the guide, §4 and §10.
