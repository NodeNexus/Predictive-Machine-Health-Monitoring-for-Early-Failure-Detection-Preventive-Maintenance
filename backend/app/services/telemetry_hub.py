"""Broadcasts telemetry payloads to connected WebSocket dashboard clients."""
from __future__ import annotations

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger("telemetry_hub")


class TelemetryHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("WebSocket client connected (%d active)" % len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("WebSocket client disconnected (%d active)" % len(self._connections))

    async def broadcast(self, payload: dict) -> None:
        dead: list[WebSocket] = []
        # Snapshot the connection set before iterating: `await
        # connection.send_json(...)` yields control, and a concurrent
        # connect()/disconnect() (e.g. a browser reconnecting) mutating
        # `self._connections` mid-iteration raises "Set changed size during
        # iteration" - an unhandled RuntimeError that silently kills the
        # calling fusion loop's task forever (discovered via real frontend
        # integration testing: React 19 StrictMode's double-effect-mount
        # opens/closes a WebSocket rapidly on every page load, reliably
        # triggering this race).
        for connection in list(self._connections):
            try:
                await connection.send_json(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)

    @property
    def active_connections(self) -> int:
        return len(self._connections)


telemetry_hub = TelemetryHub()
