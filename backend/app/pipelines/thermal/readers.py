"""Thermal frame sources.

ThermalVideoReader (demo) and LiveThermalCamera (live) both implement the
ThermalInput interface, so the analyzer downstream never knows which one
it's talking to.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.core.logging import get_logger
from app.pipelines.common.interfaces import ThermalFrame, ThermalInput

logger = get_logger("thermal.readers")


class ThermalVideoReader(ThermalInput):
    """Reads frames from a prerecorded video file (DEMO MODE).

    Frames are decoded at the video's native rate but only every Nth frame
    is *returned*, downsampled to `target_fps`, to match the configured
    processing rate and avoid analyzing redundant near-duplicate frames.
    """

    def __init__(self, path: Path | str, target_fps: float = 5.0) -> None:
        self._path = Path(path)
        self._target_fps = target_fps
        self._cap: cv2.VideoCapture | None = None
        self._native_fps: float = 0.0
        self._frame_stride: int = 1
        self._frame_index = 0
        self._returned_index = 0

    def open(self) -> None:
        if not self._path.is_file():
            raise FileNotFoundError(f"Thermal video not found: {self._path}")
        cap = cv2.VideoCapture(str(self._path))
        if not cap.isOpened():
            raise OSError(f"Could not open thermal video: {self._path}")
        self._cap = cap
        self._native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_stride = max(1, round(self._native_fps / self._target_fps))
        logger.info(
            f"Opened {self._path.name}: native_fps={self._native_fps:.2f}, "
            f"stride={self._frame_stride} (~{self._native_fps / self._frame_stride:.2f} fps effective)"
        )

    def read_frame(self) -> ThermalFrame | None:
        if self._cap is None:
            raise RuntimeError("ThermalVideoReader.open() must be called first")

        while True:
            ok, frame = self._cap.read()
            if not ok:
                return None
            index = self._frame_index
            self._frame_index += 1
            if index % self._frame_stride != 0:
                continue

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            video_time_s = index / self._native_fps if self._native_fps else 0.0
            result = ThermalFrame(
                frame_index=self._returned_index,
                timestamp=datetime.now(timezone.utc),
                image=image,
                is_radiometric=False,
                metadata={
                    "source_file": str(self._path),
                    "video_time_seconds": round(video_time_s, 3),
                    "native_frame_index": index,
                },
            )
            self._returned_index += 1
            return result

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_live(self) -> bool:
        return False

    @property
    def source_description(self) -> str:
        return f"demo:{self._path}"


class LiveThermalCamera(ThermalInput):
    """Reads frames from a USB/UVC thermal camera (LIVE MODE).

    Genuinely attempts to open the device; if it is not present, `open()`
    raises and callers must report NOT_CONNECTED rather than fabricating
    a connected state.
    """

    def __init__(self, device_index: int = 0) -> None:
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None
        self._frame_index = 0

    def open(self) -> None:
        cap = cv2.VideoCapture(self._device_index)
        if not cap.isOpened():
            cap.release()
            raise ConnectionError(f"Thermal camera not connected (device index {self._device_index})")
        self._cap = cap

    def read_frame(self) -> ThermalFrame | None:
        if self._cap is None:
            raise RuntimeError("LiveThermalCamera.open() must be called first")
        ok, frame = self._cap.read()
        if not ok:
            return None
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = ThermalFrame(
            frame_index=self._frame_index,
            timestamp=datetime.now(timezone.utc),
            image=image,
            is_radiometric=False,
            metadata={"device_index": self._device_index},
        )
        self._frame_index += 1
        return result

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_live(self) -> bool:
        return True

    @property
    def source_description(self) -> str:
        return f"live:camera(usb:{self._device_index})"
