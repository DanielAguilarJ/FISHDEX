"""
FishDex AI Server - In-process event bus
========================================
Fan-out of progress events and log records to connected dashboard WebSockets.

Two concurrency hazards are handled here:

1. ``emit`` used to iterate the listener set directly while WebSocket handlers
   could register/unregister from another task, raising
   ``RuntimeError: Set changed size during iteration``. The set is now snapshotted
   under a lock before iterating.
2. ``EventBusLogHandler`` used ``asyncio.get_running_loop()`` from whichever
   thread emitted the log record. Background identification jobs run in worker
   threads with no running loop, so every such record was silently dropped and
   the dashboard log stream appeared dead during processing. The loop is now
   captured once at startup and reached via ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Loggers whose records must never be re-published to the bus, otherwise a
# failure inside emit() would log, which would emit, which would log…
_EXCLUDED_LOGGERS = ("app.services.event_bus",)


class EventBus:
    """Process-wide publish/subscribe hub for dashboard events."""

    _instance: Optional["EventBus"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        """Return the singleton instance, constructing it at most once."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._listeners = set()
                    instance._listeners_lock = threading.Lock()
                    instance._loop = None
                    cls._instance = instance
        return cls._instance

    # ── Loop binding ────────────────────────────────────────────────────
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Record the main event loop so worker threads can schedule emissions.

        Called once from the application's lifespan startup hook.

        Args:
            loop: The loop serving HTTP/WebSocket traffic.
        """
        self._loop = loop

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Return the bound event loop, if any.

        Returns:
            The loop passed to :meth:`bind_loop`, or None before startup.
        """
        return self._loop

    # ── Subscription ────────────────────────────────────────────────────
    def register(self, queue: asyncio.Queue) -> None:
        """
        Subscribe a queue to receive serialized events.

        Args:
            queue: Bounded queue drained by a WebSocket handler.
        """
        with self._listeners_lock:
            self._listeners.add(queue)
            total = len(self._listeners)
        logger.debug("Registered event listener. Total: %d", total)

    def unregister(self, queue: asyncio.Queue) -> None:
        """
        Unsubscribe a queue.

        Args:
            queue: Queue previously passed to :meth:`register`.
        """
        with self._listeners_lock:
            self._listeners.discard(queue)
            total = len(self._listeners)
        logger.debug("Unregistered event listener. Total: %d", total)

    @property
    def listener_count(self) -> int:
        """Number of currently subscribed queues."""
        with self._listeners_lock:
            return len(self._listeners)

    # ── Publication ─────────────────────────────────────────────────────
    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """
        Broadcast an event to every subscriber.

        Slow consumers are dropped rather than allowed to block the producer.

        Args:
            event_type: Event discriminator, e.g. ``"log"`` or ``"job_progress"``.
            payload: JSON-serialisable event body.
        """
        try:
            event_str = json.dumps({"type": event_type, **payload}, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("Dropping unserialisable %s event: %s", event_type, exc)
            return

        # Snapshot under the lock: subscribers may come and go while we publish.
        with self._listeners_lock:
            listeners = tuple(self._listeners)

        stale: list[asyncio.Queue] = []
        for queue in listeners:
            try:
                queue.put_nowait(event_str)
            except asyncio.QueueFull:
                logger.warning("Listener queue full, dropping %s event", event_type)
            except RuntimeError as exc:
                # Queue bound to a closed loop — the consumer is gone.
                logger.debug("Dropping closed listener: %s", exc)
                stale.append(queue)

        for queue in stale:
            self.unregister(queue)

    def emit_threadsafe(self, event_type: str, payload: dict[str, Any]) -> bool:
        """
        Schedule :meth:`emit` from a thread that is not running the event loop.

        Args:
            event_type: Event discriminator.
            payload: JSON-serialisable event body.

        Returns:
            True when the emission was scheduled, False when no loop is
            available (e.g. during unit tests or before startup).
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return False
        try:
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.emit(event_type, payload))
            )
        except RuntimeError:
            # Loop shut down between the check and the call.
            return False
        return True


event_bus = EventBus()


class EventBusLogHandler(logging.Handler):
    """
    Logging handler that mirrors records onto the dashboard event stream.

    Works from both the event-loop thread and background worker threads.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """
        Forward one log record to the event bus.

        Args:
            record: Record produced by any logger.
        """
        if record.name.startswith(_EXCLUDED_LOGGERS):
            return
        try:
            payload = {
                "level": record.levelname,
                "message": self.format(record),
                "logger": record.name,
            }
        except Exception:  # noqa: BLE001 — logging must never raise
            self.handleError(record)
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop in this thread: we are inside a worker thread. Hand the
            # record to the main loop instead of silently discarding it.
            event_bus.emit_threadsafe("log", payload)
            return

        if running_loop.is_closed():
            return
        running_loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(event_bus.emit("log", payload))
        )
