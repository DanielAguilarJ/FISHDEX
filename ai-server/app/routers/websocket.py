import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket, secret: Optional[str] = None):
    # Validate secret in query string (unless skip_auth is enabled)
    if not settings.skip_auth:
        if not secret or secret != settings.dashboard_secret:
            logger.warning("Rejected WebSocket connection: invalid or missing dashboard secret")
            await websocket.close(code=4001)
            return

    await websocket.accept()
    logger.info("WebSocket client connected")

    queue = asyncio.Queue(maxsize=100)
    event_bus.register(queue)

    try:
        # Stream events from the queue to the client
        while True:
            event_str = await queue.get()
            await websocket.send_text(event_str)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        event_bus.unregister(queue)
