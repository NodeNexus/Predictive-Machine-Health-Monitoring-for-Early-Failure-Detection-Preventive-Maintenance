"""Device discovery: genuinely probes for hardware, never fabricates a
connected state.

Thermal cameras are probed via OpenCV (already a dependency) since USB/UVC
cameras enumerate as OpenCV VideoCapture indices on most platforms. There
is currently no vibration-DAQ or microphone-capture backend integrated
(see LiveVibrationSensor / LiveMicrophone) - those honestly report
"not_connected" with a note explaining why, rather than a fake probe.
"""
from __future__ import annotations

from typing import Literal

import cv2
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger("device_discovery")


class DeviceProbeResult(BaseModel):
    device_type: Literal["thermal_camera", "vibration_sensor", "microphone"]
    connection_type: str | None
    identifier: str
    status: Literal["connected", "not_connected"]
    configuration: dict = {}
    note: str | None = None


def probe_thermal_cameras(max_index: int = 3) -> list[DeviceProbeResult]:
    results: list[DeviceProbeResult] = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index)
        try:
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                results.append(
                    DeviceProbeResult(
                        device_type="thermal_camera",
                        connection_type="usb",
                        identifier=f"usb:{index}",
                        status="connected",
                        configuration={"width": width, "height": height, "fps": fps},
                    )
                )
        except cv2.error as exc:
            logger.warning(f"Error probing camera index {index}: {exc}")
        finally:
            cap.release()

    if not results:
        results.append(
            DeviceProbeResult(
                device_type="thermal_camera",
                connection_type="usb",
                identifier="usb:0",
                status="not_connected",
                note="No USB/UVC camera responded on the probed indices.",
            )
        )
    return results


def probe_vibration_sensors() -> list[DeviceProbeResult]:
    return [
        DeviceProbeResult(
            device_type="vibration_sensor",
            connection_type=None,
            identifier="daq:0",
            status="not_connected",
            note="No DAQ backend integrated yet (see LiveVibrationSensor) - cannot probe real hardware.",
        )
    ]


def probe_microphones() -> list[DeviceProbeResult]:
    return [
        DeviceProbeResult(
            device_type="microphone",
            connection_type=None,
            identifier="mic:0",
            status="not_connected",
            note="No audio-capture backend integrated yet (see LiveMicrophone) - cannot probe real hardware.",
        )
    ]


def discover_all() -> list[DeviceProbeResult]:
    return [*probe_thermal_cameras(), *probe_vibration_sensors(), *probe_microphones()]
