"""
FishDex AI Server - Dashboard event stream
==========================================
WebSocket endpoint that streams server events and log records to the operator
dashboard.

Authentication accepts the dashboard secret either as the
``X-FishDex-Dashboard-Secret`` header (preferred) or as a ``secret`` query
parameter (kept for the existing dashboard). Query strings are logged by proxies
and retained in browser history, so the header is the better transport.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.security import constant_time_compare
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# Per-listener buffer. Bounded so one stalled dashboard cannot grow unbounded.
_QUEUE_MAX_SIZE = 100

# Upper bound on simultaneous dashboard listeners. Prevents an unauthenticated
# flood from exhausting memory before the secret check can reject it.
_MAX_CONCURRENT_LISTENERS = 20

# WebSocket close codes (RFC 6455 private range).
_CLOSE_UNAUTHORIZED = 4001
_CLOSE_TOO_MANY_CONNECTIONS = 4029


def _is_authorized(header_secret: Optional[str], query_secret: Optional[str]) -> bool:
    """
    Check the dashboard secret in constant time.

    Args:
        header_secret: Value of ``X-FishDex-Dashboard-Secret``.
        query_secret: Value of the ``secret`` query parameter.

    Returns:
        True when either credential matches, or when auth is disabled for dev.
    """
    if settings.skip_auth:
        return True
    if constant_time_compare(header_secret, settings.dashboard_secret):
        return True
    return constant_time_compare(query_secret, settings.dashboard_secret)


@router.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    secret: Optional[str] = Query(default=None),
) -> None:
    """
    Stream server events to an authenticated dashboard client.

    Args:
        websocket: The client connection.
        secret: Dashboard secret supplied as a query parameter (legacy path).
    """
    header_secret = websocket.headers.get("X-FishDex-Dashboard-Secret")

    if not _is_authorized(header_secret, secret):
        logger.warning(
            "Rejected WebSocket connection: invalid or missing dashboard secret"
        )
        await websocket.close(code=_CLOSE_UNAUTHORIZED)
        return

    if event_bus.listener_count >= _MAX_CONCURRENT_LISTENERS:
        logger.warning(
            "Rejected WebSocket connection: %d listeners already attached",
            event_bus.listener_count,
        )
        await websocket.close(code=_CLOSE_TOO_MANY_CONNECTIONS)
        return

    await websocket.accept()
    logger.info("WebSocket client connected")

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
    event_bus.register(queue)

    try:
        while True:
            event_str = await queue.get()
            await websocket.send_text(event_str)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except asyncio.CancelledError:
        # Server shutdown: propagate so the task terminates promptly.
        raise
    except Exception as exc:  # noqa: BLE001 — never let one client kill the app
        logger.error("WebSocket connection error: %s", exc, exc_info=True)
    finally:
        event_bus.unregister(queue)
