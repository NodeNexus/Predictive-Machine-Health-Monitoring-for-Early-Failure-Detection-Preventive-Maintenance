"""Resolve file paths recorded in manifests and the dataset registry.

Manifests and the registry store absolute paths from the machine that generated them
(for example C:\\Users\\...\\Desktop\\MECHANICAL\\_thermal_audit_ds1\\...). When the project
has moved, those paths no longer exist. This re-roots such a path onto this checkout,
keeping the part after the project folder name. Paths that exist are returned unchanged.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_FOLDER = "MECHANICAL"


def resolve_recorded_path(recorded: str) -> Path:
    path = Path(recorded)
    if path.exists():
        return path
    parts = [p for p in re.split(r"[\\/]+", recorded) if p]
    if PROJECT_FOLDER in parts:
        last = len(parts) - 1 - parts[::-1].index(PROJECT_FOLDER)
        rest = parts[last + 1:]
        if rest:
            return REPO_ROOT.joinpath(*rest)
    return path
