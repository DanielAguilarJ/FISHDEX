"""
Dashboard event stream.

The WebSocket carries live job progress and log lines to the operator dashboard.
Three properties matter and none of them is obvious from the happy path:

* it is authenticated *before* accepting the connection, so an unauthorised client
  never gets a socket and never reaches the event bus;
* the listener count is capped, so an unauthenticated flood cannot exhaust memory
  by opening sockets faster than they are rejected;
* every exit path unregisters the queue, or the bus accumulates dead listeners and
  publishes into queues nobody drains.

The bus itself is also covered here: it is shared mutable state written from both
the event loop and background worker threads, which is where its two historical
defects came from.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.routers import websocket as ws_module
from app.routers.websocket import (
    _CLOSE_TOO_MANY_CONNECTIONS,
    _CLOSE_UNAUTHORIZED,
    _MAX_CONCURRENT_LISTENERS,
    _is_authorized,
)
from app.services.event_bus import EventBus, event_bus

DASHBOARD_SECRET = "ws-dashboard-secret"


@pytest.fixture(autouse=True)
def isolated_bus(monkeypatch: pytest.MonkeyPatch):
    """
    Detach every listener around each test.

    The bus is a process-wide singleton, so a leaked queue from one test would
    change the listener count another test asserts on.
    """
    monkeypatch.setattr(settings, "dashboard_secret", DASHBOARD_SECRET, raising=False)
    monkeypatch.setattr(settings, "skip_auth", False, raising=False)
    for queue in tuple(event_bus._listeners):
        event_bus.unregister(queue)
    yield
    for queue in tuple(event_bus._listeners):
        event_bus.unregister(queue)


@pytest.fixture
def client() -> TestClient:
    """TestClient over the websocket router."""
    app = FastAPI()
    app.include_router(ws_module.router)
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Authorisation predicate
# ─────────────────────────────────────────────────────────────────────────────
def test_header_secret_is_accepted() -> None:
    assert _is_authorized(DASHBOARD_SECRET, None) is True


def test_query_secret_is_accepted() -> None:
    """Kept for the existing dashboard, though the header is preferred."""
    assert _is_authorized(None, DASHBOARD_SECRET) is True


def test_wrong_secret_is_refused() -> None:
    assert _is_authorized("nope", None) is False
    assert _is_authorized(None, "nope") is False


def test_absent_secret_is_refused() -> None:
    assert _is_authorized(None, None) is False


def test_empty_secret_is_refused() -> None:
    """An empty string must not compare equal to a configured secret."""
    assert _is_authorized("", None) is False


def test_skip_auth_bypasses_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development bypass; refused outright when environment is production."""
    monkeypatch.setattr(settings, "skip_auth", True, raising=False)

    assert _is_authorized(None, None) is True


# ─────────────────────────────────────────────────────────────────────────────
# Connection handshake
# ─────────────────────────────────────────────────────────────────────────────
def test_connection_without_a_secret_is_closed(client: TestClient) -> None:
    """
    Rejected before accept(), so an unauthorised client never gets a socket and
    never reaches the event bus.
    """
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/events"):
            pass

    assert excinfo.value.code == _CLOSE_UNAUTHORIZED


def test_connection_with_a_wrong_secret_is_closed(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/events?secret=wrong"):
            pass

    assert excinfo.value.code == _CLOSE_UNAUTHORIZED


def test_connection_with_the_query_secret_succeeds(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/events?secret={DASHBOARD_SECRET}") as socket:
        assert socket is not None


def test_connection_with_the_header_secret_succeeds(client: TestClient) -> None:
    """
    The preferred transport: a query string ends up in proxy access logs and
    browser history.
    """
    with client.websocket_connect(
        "/ws/events", headers={"X-FishDex-Dashboard-Secret": DASHBOARD_SECRET}
    ) as socket:
        assert socket is not None


def test_a_rejected_connection_leaves_no_listener(client: TestClient) -> None:
    """The count must not move, or a rejection loop would still exhaust the bus."""
    before = event_bus.listener_count

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/events"):
            pass

    assert event_bus.listener_count == before


def test_the_listener_cap_is_enforced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Saturate the bus, then confirm the next connection is refused with the
    too-many-connections code rather than accepted.
    """
    fillers = [asyncio.Queue(maxsize=1) for _ in range(_MAX_CONCURRENT_LISTENERS)]
    for queue in fillers:
        event_bus.register(queue)
    try:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/ws/events?secret={DASHBOARD_SECRET}"):
                pass
        assert excinfo.value.code == _CLOSE_TOO_MANY_CONNECTIONS
    finally:
        for queue in fillers:
            event_bus.unregister(queue)


def test_disconnecting_unregisters_the_listener(client: TestClient) -> None:
    """
    The finally block is what prevents the bus accumulating dead listeners and
    publishing into queues nobody drains.
    """
    before = event_bus.listener_count

    with client.websocket_connect(f"/ws/events?secret={DASHBOARD_SECRET}"):
        pass

    assert event_bus.listener_count == before


# ─────────────────────────────────────────────────────────────────────────────
# Event bus
# ─────────────────────────────────────────────────────────────────────────────
def test_bus_is_a_singleton() -> None:
    assert EventBus() is EventBus() is event_bus


def test_register_and_unregister_move_the_count() -> None:
    queue: asyncio.Queue[str] = asyncio.Queue()
    before = event_bus.listener_count

    event_bus.register(queue)
    assert event_bus.listener_count == before + 1

    event_bus.unregister(queue)
    assert event_bus.listener_count == before


def test_unregistering_twice_is_harmless() -> None:
    """
    Called from a finally block that may run after an error already removed the
    queue, so it must be idempotent.
    """
    queue: asyncio.Queue[str] = asyncio.Queue()
    event_bus.register(queue)

    event_bus.unregister(queue)
    event_bus.unregister(queue)

    assert queue not in event_bus._listeners


def test_registering_the_same_queue_twice_counts_once() -> None:
    """A set, so a double register cannot deliver each event twice."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    before = event_bus.listener_count

    event_bus.register(queue)
    event_bus.register(queue)

    assert event_bus.listener_count == before + 1
    event_bus.unregister(queue)


def test_emit_delivers_to_every_listener() -> None:
    """Two dashboards open at once must both receive the event."""

    async def scenario() -> tuple[str, str]:
        first: asyncio.Queue[str] = asyncio.Queue()
        second: asyncio.Queue[str] = asyncio.Queue()
        event_bus.register(first)
        event_bus.register(second)
        try:
            await event_bus.emit("job_progress", {"job_id": "job-1", "progress": 50})
            return first.get_nowait(), second.get_nowait()
        finally:
            event_bus.unregister(first)
            event_bus.unregister(second)

    left, right = asyncio.run(scenario())

    assert left == right
    assert "job-1" in left


def test_emit_includes_the_event_type() -> None:
    async def scenario() -> str:
        queue: asyncio.Queue[str] = asyncio.Queue()
        event_bus.register(queue)
        try:
            await event_bus.emit("log", {"level": "INFO", "message": "hello"})
            return queue.get_nowait()
        finally:
            event_bus.unregister(queue)

    import json

    payload = json.loads(asyncio.run(scenario()))

    assert payload["type"] == "log"
    assert payload["message"] == "hello"


def test_emit_drops_events_for_a_full_queue_without_blocking() -> None:
    """
    A stalled dashboard must not back-pressure the identification pipeline, which
    is what publishes the progress events.
    """

    async def scenario() -> int:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        event_bus.register(queue)
        try:
            await event_bus.emit("log", {"n": 1})
            await event_bus.emit("log", {"n": 2})
            await event_bus.emit("log", {"n": 3})
            return queue.qsize()
        finally:
            event_bus.unregister(queue)

    assert asyncio.run(scenario()) == 1


def test_emit_survives_an_unserialisable_payload() -> None:
    """
    Publishing must never raise into the caller: it is called from the middle of
    job processing.
    """

    async def scenario() -> bool:
        queue: asyncio.Queue[str] = asyncio.Queue()
        event_bus.register(queue)
        try:
            await event_bus.emit("log", {"obj": object()})
            return True
        finally:
            event_bus.unregister(queue)

    assert asyncio.run(scenario()) is True


def test_emit_with_no_listeners_is_a_noop() -> None:
    async def scenario() -> None:
        await event_bus.emit("log", {"message": "nobody listening"})

    asyncio.run(scenario())


def test_emit_snapshots_listeners_before_iterating() -> None:
    """
    The regression this covers: emit() iterated the listener set directly while a
    WebSocket handler could register concurrently, risking
    'RuntimeError: Set changed size during iteration'.
    """

    async def scenario() -> None:
        queues = [asyncio.Queue() for _ in range(5)]
        for queue in queues:
            event_bus.register(queue)
        try:
            # Register another listener from inside the emit's await window.
            extra: asyncio.Queue[str] = asyncio.Queue()

            async def late_join() -> None:
                event_bus.register(extra)

            await asyncio.gather(event_bus.emit("log", {"n": 1}), late_join())
            event_bus.unregister(extra)
        finally:
            for queue in queues:
                event_bus.unregister(queue)

    asyncio.run(scenario())


def test_emit_threadsafe_returns_false_without_a_bound_loop() -> None:
    """
    Background worker threads have no running loop. Before the fix this path
    swallowed a RuntimeError and silently dropped every progress event.
    """
    original = event_bus._loop
    event_bus._loop = None
    try:
        assert event_bus.emit_threadsafe("job_progress", {"job_id": "x"}) is False
    finally:
        event_bus._loop = original


def test_emit_threadsafe_schedules_onto_the_bound_loop() -> None:
    """With a loop bound at startup, a worker thread can publish."""

    async def scenario() -> str:
        loop = asyncio.get_running_loop()
        event_bus.bind_loop(loop)
        queue: asyncio.Queue[str] = asyncio.Queue()
        event_bus.register(queue)
        try:
            assert event_bus.emit_threadsafe("job_progress", {"job_id": "job-9"}) is True
            # Give the scheduled task a turn.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return queue.get_nowait()
        finally:
            event_bus.unregister(queue)

    assert "job-9" in asyncio.run(scenario())


def test_bound_loop_is_readable() -> None:
    async def scenario() -> bool:
        loop = asyncio.get_running_loop()
        event_bus.bind_loop(loop)
        return event_bus.get_loop() is loop

    assert asyncio.run(scenario()) is True
