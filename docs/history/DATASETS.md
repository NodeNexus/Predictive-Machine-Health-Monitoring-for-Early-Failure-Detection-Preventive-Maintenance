# Datasets

This document records what was actually found by inspecting the downloaded
data (`backend/app/datasets/scanner.py`, run via `scripts/scan_datasets.py`).
Nothing here is inferred — every number was read from the files themselves.
Regenerate the manifest with:

```
cd backend
./.venv/Scripts/python.exe ../scripts/scan_datasets.py
```

This writes `data/manifests/dataset_manifest.json` and upserts
`DatasetRegistry` rows in the SQLite DB, which the `/api/datasets` endpoint
serves.

## Acoustic (MIMII / DCASE-style, WAV)

All five datasets are mono, 16-bit PCM, **16 kHz**, ~10s clips. Two labelling
conventions were found and both are handled by the scanner:

- DCASE-style (`bearing`, `fan`, `valve`, `gearbox`): filenames contain
  `..._train_normal_...` or `..._test_{normal|anomaly}_...`. A per-dataset
  `attributes_NN.csv` also exists but is not currently parsed (it records
  operating condition, e.g. velocity/voltage — candidate for machine-specific
  model conditioning later, not required for Phase 2).
- MIMII-style (`dev_data_pump`): filenames start with `normal_...` or
  `anomaly_...`, no attributes CSV.

Train subsets are **normal-only** in every dataset (fits an anomaly-detection
training setup, not a balanced classifier). Observed counts:

| Dataset | Total WAVs | Normal | Anomaly | Unlabeled |
|---|---|---|---|---|
| bearing | 3599 | 3299 | 300 | 0 |
| fan | 3600 | 3300 | 300 | 0 |
| valve | 3600 | 3300 | 300 | 0 |
| gearbox | 3600 | 3300 | 300 | 0 |
| dev_data_pump | 4205 | 3749 | 456 | 0 |

## Vibration — IMS bearing run-to-failure dataset

Source: `DATASET/IMS/IMS/{1st,2nd,3rd}_test.rar` (extracted). Per the vendor
README (`DATASET/IMS/IMS/Readme Document for IMS Bearing Data.pdf`):
4 bearings on a shaft at constant 2000 RPM, 6000 lb radial load, 20 kHz
sample rate, 20,480-point (~1.024s) snapshot per file, ASCII tab-separated.

| Set | Channels | Files (README) | Files (observed) | Failure |
|---|---|---|---|---|
| 1st_test | 8 (2/bearing) | 2156 | 2156 ✓ | inner race (brg 3), roller element (brg 4) |
| 2nd_test | 4 (1/bearing) | 984 | 984 ✓ | outer race (brg 1) |
| 3rd_test | 4 (1/bearing) | 4448 | **6324 ✗** | outer race (brg 3) |

**Discrepancy:** the 3rd test set's archive extracts to a folder literally
named `4th_test` (a known quirk of the original data package — not a
separate 4th dataset), and its observed file count (6324) does not match the
README's stated 4448. This is flagged in the manifest `notes` field rather
than silently trusted. Treat the observed count as authoritative until
someone manually reconciles it against the paper.

This is **run-to-failure degradation data, not per-file labelled
anomaly/normal data** — only "the bearing failed by the end of the
experiment" is documented, and which specific files within a run count as
"already faulty" is not given. Any anomaly-detection use of this dataset
must derive its own labels (e.g. by time-to-failure or a health-index
threshold), and must not claim ground-truth per-file labels that don't exist.

## Thermal — demo videos

8 MP4s in `VIDEO/`, all regular RGB video (H.264-style container) — these
are **recordings of a thermal camera's display output**, not raw radiometric
sensor data. No calibration/temperature-scale metadata is embedded. They are
treated strictly as `is_radiometric=False` visible-light footage of thermal
imagery per the honesty policy in `docs/history/ARCHITECTURE.md`. Observed
properties (resolution / fps / duration) are in the manifest; most are
1920×1080 @ ~30fps, one is 854×480 @ 24fps, one is 1920×1080 @ 60fps.

## Explicitly out of scope / not usable yet

- **`DATASET/ToyADMOS-dataset-master/`** contains only the GitHub repo of
  scripts, anomaly-condition spreadsheets, and documentation for the
  ToyADMOS dataset — **it contains zero actual WAV audio files**. The real
  audio archives are hosted separately (Zenodo) and were not downloaded.
  Do not treat this directory as usable acoustic data.
- **`DATASET/5.+Battery+Data+Set/`** (NASA battery aging data) is unrelated
  to the thermal/vibration/acoustic machine-health scope of this product.
  It was extracted (6 zips) but is intentionally excluded from the dataset
  scanner/registry.
- **`DATASET/4.+Bearings/`** is a duplicate copy of the same IMS `.rar`
  archives already extracted under `DATASET/IMS/IMS/` — not scanned
  separately to avoid double-registering the same data.
