from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.services.telemetry_hub import telemetry_hub

logger = get_logger("websocket")
router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_socket(websocket: WebSocket) -> None:
    await telemetry_hub.connect(websocket)
    try:
        while True:
            # Dashboard clients don't need to send anything; we just keep
            # the connection alive and detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_hub.disconnect(websocket)
