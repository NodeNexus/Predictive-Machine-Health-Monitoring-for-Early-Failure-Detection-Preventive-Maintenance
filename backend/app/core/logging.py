"""Structured logging setup.

Every log record is emitted as a single JSON line carrying:
timestamp, component, machine_id, event_type, severity, message,
and exception info where applicable.
"""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": record.name,
            "severity": record.levelname,
            "message": record.getMessage(),
        }
        for field in ("machine_id", "event_type"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("idealab")
    if root.handlers:
        return  # already configured
    root.setLevel(level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(StructuredFormatter())
    root.addHandler(stream_handler)

    log_file = Path(settings.log_dir) / "idealab.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(StructuredFormatter())
    root.addHandler(file_handler)


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"idealab.{component}")
