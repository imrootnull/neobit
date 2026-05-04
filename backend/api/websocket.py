"""
WebSocket endpoint — real-time event streaming to dashboard clients.
Supports both local and cloud dashboard connections.
"""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.event_bus import event_bus
from backend.core.stream_manager import stream_manager
from backend.utils.hardware import get_system_info
from loguru import logger

router = APIRouter(tags=["WebSocket"])


class WSClient:
    """Wraps a WebSocket connection with send_json helper."""
    def __init__(self, ws: WebSocket, client_id: str):
        self.ws = ws
        self.client_id = client_id

    async def send_json(self, data: dict):
        await self.ws.send_json(data)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = f"{websocket.client.host}:{websocket.client.port}"
    client = WSClient(websocket, client_id)
    event_bus.register_ws_client(client)
    logger.info(f"🔌 WS client connected: {client_id}")

    try:
        # Send initial state on connect
        await websocket.send_json({
            "type": "init",
            "data": {
                "streams": stream_manager.get_all_status(),
                "system": get_system_info(),
            }
        })

        # Keep-alive loop — also push stream heartbeat every 5s
        while True:
            try:
                # Wait for client messages (ping/pong or commands)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                msg = json.loads(data)

                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg.get("type") == "subscribe_camera":
                    # Client can subscribe to specific camera updates
                    cam_id = msg.get("camera_id")
                    status = stream_manager.get_status(cam_id)
                    await websocket.send_json({"type": "camera_status", "data": status})

            except asyncio.TimeoutError:
                # Push heartbeat with stream statuses
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {
                        "streams": stream_manager.get_all_status(),
                    }
                })

    except WebSocketDisconnect:
        logger.info(f"🔌 WS client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WS error ({client_id}): {e}")
    finally:
        event_bus.unregister_ws_client(client)
