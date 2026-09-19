#!/usr/bin/env python
"""CLI entry point: scan DATASET/ + VIDEO/, write a manifest, sync the DB registry.

Usage (from backend/, with the venv active):
    python ../scripts/scan_datasets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.database.session import SessionLocal, init_db  # noqa: E402
from app.datasets.registry import sync_to_db, write_manifest_file  # noqa: E402
from app.datasets.scanner import scan_all  # noqa: E402


def main() -> None:
    init_db()

    entries = scan_all(settings.dataset_dir, settings.video_dir)

    manifest_path = settings.manifest_dir / "dataset_manifest.json"
    write_manifest_file(entries, manifest_path)

    db = SessionLocal()
    try:
        sync_to_db(entries, db, manifest_path)
    finally:
        db.close()

    print(f"Scanned {len(entries)} dataset(s). Manifest written to {manifest_path}")
    for e in entries:
        label = f"{e.normal_count or 0}N/{e.anomaly_count or 0}A" if e.modality == "acoustic" else "-"
        print(f"  [{e.modality:9s}] {e.dataset_name:20s} samples={e.sample_count!s:>6} labels={label} sr={e.sample_rate}")


if __name__ == "__main__":
    main()
