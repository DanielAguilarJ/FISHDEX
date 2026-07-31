"""
FishDex AI Server - Main Application
====================================
FastAPI entry point: logging, CORS, rate limiting, startup hooks and health probes.

Run with::

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Awaitable
from typing import Any, Callable

from fastapi import FastAPI, Request
from starlette.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import SERVICE_VERSION, settings
from app.database import init_db
from app.middleware.correlation import CorrelationFilter, CorrelationMiddleware
from app.routers import auth, dashboard, identify, jobs, sightings, websocket
from app.services.event_bus import EventBusLogHandler, event_bus
from app.services.retry_service import start_retry_service
from app.services.system_monitor import start_system_monitor


def _configure_logging() -> None:
    """
    Install structured stdout logging with correlation-ID support.

    The correlation filter must be attached to the **handlers**, not to the root
    logger. Python only applies a logger's filters to records emitted through
    that logger; records propagated from child loggers reach ancestor *handlers*
    but skip ancestor *filters*. The previous code added the filter to the root
    logger, so ``%(correlation_id)s`` was always the placeholder ``"-"`` and
    request tracing never worked.
    """
    # A record factory guarantees the attribute exists even for records emitted
    # by third-party libraries that bypass our handlers.
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        """
        Create a log record that always carries a correlation_id attribute.

        Returns:
            The record, with a placeholder ID when none is set.
        """
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "-"
        return record

    logging.setLogRecordFactory(record_factory)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-8s  [%(correlation_id)s]  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    stream_handler.addFilter(CorrelationFilter())

    dashboard_handler = EventBusLogHandler()
    dashboard_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    dashboard_handler.addFilter(CorrelationFilter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Replace any handler installed by a previous import of this module so that
    # re-importing under pytest does not duplicate every log line.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(stream_handler)
    root.addHandler(dashboard_handler)


_configure_logging()
logger = logging.getLogger("fishdex")

# ─── Rate limiter (slowapi) ─────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ─── Server start time (for uptime reporting) ───────────────────────────
_server_start_time: float = 0.0

# ─── Simple request counter ─────────────────────────────────────────────
_request_count: int = 0


def get_server_start_time() -> float:
    """Return the server start epoch timestamp."""
    return _server_start_time


def get_request_count() -> int:
    """Return the total number of requests served."""
    return _request_count


def increment_request_count() -> None:
    """Increment the global request counter."""
    global _request_count
    _request_count += 1


# ─────────────────────────────────────────────────────────────────────────────
# Startup helpers
# ─────────────────────────────────────────────────────────────────────────────
def _assert_production_secrets() -> None:
    """
    Refuse to serve production traffic with placeholder secrets.

    Raises:
        RuntimeError: One or more secrets still hold a build-time placeholder.
    """
    if not settings.is_production:
        return
    placeholders = settings.placeholder_secret_names()
    if placeholders:
        raise RuntimeError(
            "FATAL: the following secrets hold default/placeholder values in "
            f"production: {', '.join(placeholders)}. Override them before deploying."
        )


def _ensure_data_directories() -> None:
    """Create every directory the server writes to."""
    for path in (
        settings.server_data_dir,
        settings.temp_dir,
        settings.cache_dir,
        settings.private_data_dir,
        settings.fish_documents_dir,
        settings.fish_media_dir,
        settings.job_artifacts_dir,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
    Path(settings.embeddings_db_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info("Data directories ready: %s", settings.server_data_dir)


def _preload_models() -> None:
    """
    Load every inference model once, at startup.

    Keeps the first user request from paying the model load cost, and surfaces a
    missing or corrupt checkpoint in the logs immediately rather than on the
    first capture.
    """
    loaders: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("OBB detector", _load_detector_service),
        ("species classifier", _load_classifier_service),
        ("FishEncoder ReID model", _load_reid_service),
    )
    for label, loader in loaders:
        try:
            logger.info("%s: available=%s", label, loader())
        except Exception as exc:  # noqa: BLE001 — startup must not abort on one model
            logger.warning("Could not pre-load %s: %s", label, exc, exc_info=True)


def _load_detector_service() -> bool:
    """Instantiate the OBB detector service. Returns its availability."""
    from app.services.detector_service import get_detector_service

    return bool(get_detector_service().available)


def _load_classifier_service() -> bool:
    """Instantiate the species classifier service. Returns its availability."""
    from app.services.classifier_service import get_classifier_service

    return bool(get_classifier_service().available)


def _load_reid_service() -> bool:
    """Instantiate the FishEncoder ReID service. Returns whether weights loaded."""
    from app.services.reid_embedding_service import get_reid_embedding_service

    return bool(get_reid_embedding_service().is_loaded)


# ─── Startup / Shutdown lifecycle ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Run startup tasks before serving and clean up on shutdown.

    Args:
        app: The FastAPI application (unused, required by the protocol).
    """
    global _server_start_time
    _server_start_time = time.time()

    _assert_production_secrets()

    # Give background worker threads a handle on this loop so they can publish
    # progress events to the dashboard.
    event_bus.bind_loop(asyncio.get_running_loop())

    start_system_monitor()
    start_retry_service()
    init_db()
    _ensure_data_directories()
    _preload_models()

    logger.info(
        "=== FishDex AI Server v%s started ===  threshold=%.2f  radius=%.1fkm  data=%s",
        SERVICE_VERSION,
        settings.similarity_threshold,
        settings.nearby_area_radius_km,
        settings.server_data_dir,
    )

    yield  # ← app is running

    logger.info("=== FishDex AI Server shutting down ===")


# ─── Create FastAPI app ──────────────────────────────────────────────────
app = FastAPI(
    title="FishDex AI Server",
    description="Fish identification API with 7-step pipeline for the FishDex app",
    version=SERVICE_VERSION,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# Rate limiter — store on app.state so routers can access it
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Correlation ID middleware (outermost — added first, runs last) ───────
app.add_middleware(CorrelationMiddleware)

# CORS. Native mobile clients ignore CORS entirely, so a wildcard buys nothing
# and — combined with allow_credentials — lets any web page issue authenticated
# requests on a logged-in user's behalf. Origins are therefore explicit in
# production; see FISHDEX_CORS_ALLOWED_ORIGINS.
_cors_origins = settings.resolved_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Credentials cannot be combined with a wildcard origin per the CORS spec.
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-FishDex-Client-Secret",
        "X-FishDex-Dashboard-Secret",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID"],
)

# Register routers
app.include_router(identify.router, prefix="/api/v1", tags=["Identification"])
app.include_router(jobs.router)  # jobs.router already defines prefix="/api/v1/jobs"
app.include_router(dashboard.router)
app.include_router(websocket.router)
app.include_router(auth.router)
app.include_router(sightings.router)

# Mount local storage folder to serve frames and videos directly.
# Unauthenticated by design in development only; in production media must be
# served through an authenticated endpoint or signed URLs.
storage_path = Path(settings.server_data_dir) / "storage"
storage_path.mkdir(parents=True, exist_ok=True)
if not settings.is_production:
    app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")
else:
    logger.warning(
        "PUBLIC /storage mount DISABLED in production. "
        "Serve media through an authenticated endpoint or a reverse proxy with signed URLs."
    )


@app.middleware("http")
async def count_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    Count every served request.

    The counter previously only advanced inside ``/health``, making the reported
    ``request_count`` meaningless.

    Args:
        request: Incoming request.
        call_next: Downstream ASGI handler.

    Returns:
        The downstream response.
    """
    increment_request_count()
    return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
# Readiness sub-checks — each returns (checks_fragment, is_ready)
# ─────────────────────────────────────────────────────────────────────────────
def _check_database() -> tuple[dict[str, Any], bool]:
    """
    Verify the operational database answers a trivial query.

    Returns:
        Tuple of (check fragment, readiness flag). The underlying exception text
        is logged rather than returned, to avoid leaking paths to unauthenticated
        callers.
    """
    from app.database import get_db_connection

    try:
        conn = get_db_connection()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        logger.error("Readiness: database check failed: %s", exc, exc_info=True)
        return {"db_accessible": False}, False
    return {"db_accessible": True}, True


def _check_migrations() -> dict[str, Any]:
    """
    Report the applied migration version.

    Returns:
        Check fragment with ``db_migration_version``.
    """
    from app.database import get_db_connection
    from app.migrations.runner import get_current_version

    try:
        conn = get_db_connection()
        try:
            return {"db_migration_version": get_current_version(conn)}
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        logger.warning("Readiness: migration version unavailable: %s", exc)
        return {"db_migration_version": 0}


def _check_models() -> tuple[dict[str, Any], bool]:
    """
    Verify the detector and the ReID encoder are loaded.

    Returns:
        Tuple of (check fragment, readiness flag).
    """
    checks: dict[str, Any] = {}
    ready = True

    try:
        from app.services.detector_service import get_detector_service

        checks["detector_loaded"] = bool(get_detector_service().available)
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness: detector unavailable: %s", exc)
        checks["detector_loaded"] = False
    ready &= bool(checks["detector_loaded"])

    try:
        from app.services.reid_embedding_service import get_reid_embedding_service

        checks["reid_model_loaded"] = bool(get_reid_embedding_service().is_loaded)
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness: ReID model unavailable: %s", exc)
        checks["reid_model_loaded"] = False
    ready &= bool(checks["reid_model_loaded"])

    try:
        from app.services.model_fingerprint_service import (
            get_model_fingerprint,
            get_model_version,
        )

        checks["reid_model_version"] = get_model_version()
        checks["embedding_dimensions"] = get_model_fingerprint().embedding_dim
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness: model fingerprint unavailable: %s", exc)
        checks["reid_model_version"] = None

    return checks, ready


def _count_active_embeddings() -> dict[str, Any]:
    """
    Count gallery entries for the active model version.

    Queries the matching service once; the previous implementation issued the
    same aggregate query twice.

    Returns:
        Check fragment describing the active gallery, or zeros on failure.
    """
    try:
        from app.services.matching_service import get_matching_service

        active_version = settings.reid_cache_name
        counts = get_matching_service().count_active_embeddings(active_version)
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness: embedding count failed: %s", exc)
        return {"active_embeddings": 0, "active_fish": 0, "index_complete": False}

    checks: dict[str, Any] = {
        "active_model_version": settings.reid_cache_name,
        "active_embeddings": counts["embedding_count"],
        "active_fish": counts["fish_count"],
        "active_sightings_with_embedding": counts["sighting_count"],
        "index_complete": counts["embedding_count"] > 0,
        "fingerprint_enabled": settings.reid_fingerprint_crop_enabled,
    }
    if settings.reid_fingerprint_crop_enabled:
        checks["fingerprint_bounds"] = {
            "x_start": settings.reid_fingerprint_x_start,
            "x_end": settings.reid_fingerprint_x_end,
            "y_start": settings.reid_fingerprint_y_start,
            "y_end": settings.reid_fingerprint_y_end,
        }
    return checks


def _check_calibration() -> dict[str, Any]:
    """
    Report whether a validated matching calibration is loaded.

    Returns:
        Check fragment describing calibration state.
    """
    try:
        from app.calibration import is_calibration_valid, load_calibration

        calibration = load_calibration(settings.reid_cache_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness: calibration unavailable: %s", exc)
        return {
            "calibration_loaded": False,
            "calibration_validated": False,
            "calibration_validation_reason": "Exception during calibration check",
        }

    if calibration is None:
        return {
            "calibration_loaded": False,
            "calibration_validated": False,
            "calibration_validation_reason": "No calibration loaded",
            "calibration_validation_far": None,
            "calibration_test_far": None,
        }

    is_valid, reason = is_calibration_valid(calibration)
    return {
        "calibration_loaded": True,
        "calibration_validated": is_valid,
        "calibration_validation_reason": reason,
        "calibration_validation_far": calibration.validation_far,
        "calibration_test_far": calibration.test_far,
    }


def _check_area_catalog() -> tuple[dict[str, Any], bool]:
    """
    Verify the Czech fishing-area catalog is importable and non-empty.

    Returns:
        Tuple of (check fragment, readiness flag).
    """
    try:
        from app.data.czech_areas import CZECH_AREAS

        count = len(CZECH_AREAS)
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness: Czech area catalog failed to load: %s", exc)
        return {"czech_areas_loaded": 0}, False
    return {"czech_areas_loaded": count}, count > 0


# ─── Root endpoints ─────────────────────────────────────────────────────
@app.get("/health/live", tags=["System"])
async def health_live() -> dict[str, bool]:
    """
    Liveness probe.

    Returns:
        ``{"alive": True}`` as long as the process can serve requests.
    """
    return {"alive": True}


@app.get("/health/ready", tags=["System"])
async def health_ready() -> JSONResponse:
    """
    Readiness probe verifying the full identification pipeline.

    Returns:
        JSON body with per-component checks, and HTTP 503 when any critical
        component is not ready.
    """
    checks: dict[str, Any] = {}
    ready = True

    db_checks, db_ready = _check_database()
    checks.update(db_checks)
    ready &= db_ready

    checks.update(_check_migrations())

    model_checks, models_ready = _check_models()
    checks.update(model_checks)
    ready &= models_ready

    checks.update(_count_active_embeddings())
    checks.update(_check_calibration())

    area_checks, areas_ready = _check_area_catalog()
    checks.update(area_checks)
    ready &= areas_ready

    checks["auto_match_enabled"] = bool(checks.get("calibration_validated")) and bool(
        checks.get("index_complete")
    )
    checks["match_radius_km"] = settings.nearby_area_radius_km
    checks["reid_similarity_threshold"] = settings.reid_similarity_threshold

    return JSONResponse(
        content={"ready": ready, **checks}, status_code=200 if ready else 503
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """
    Quick health check.

    Use ``/health/ready`` for the full pipeline check.

    Returns:
        Service name, version, uptime, detector availability and request count.
    """
    uptime_seconds = (
        round(time.time() - _server_start_time, 1) if _server_start_time else 0.0
    )

    try:
        from app.services.detector_service import get_loaded_detector_service

        detector = get_loaded_detector_service()
        detector_loaded = detector is not None and bool(detector.available)
    except Exception as exc:  # noqa: BLE001 — health must never raise
        logger.warning("Health: detector status unavailable: %s", exc)
        detector_loaded = False

    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": SERVICE_VERSION,
        "uptime_seconds": uptime_seconds,
        "detector_loaded": detector_loaded,
        "request_count": _request_count,
    }


@app.get("/", tags=["System"], response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """
    Serve the operator dashboard shell.

    The dashboard's own API calls are authenticated separately with the dashboard
    secret, so serving the static shell here discloses no data.

    Returns:
        The dashboard HTML, or a 404 placeholder when the file is absent.
    """
    dashboard_html = _read_dashboard_html()
    if dashboard_html is None:
        return HTMLResponse(content="<h1>Dashboard HTML not found</h1>", status_code=404)
    return HTMLResponse(content=dashboard_html)


_dashboard_html_cache: str | None = None


def _read_dashboard_html() -> str | None:
    """
    Read and memoise the dashboard HTML.

    Returns:
        File contents, or None when the file does not exist.
    """
    global _dashboard_html_cache
    if _dashboard_html_cache is not None:
        return _dashboard_html_cache

    dashboard_path = Path(__file__).parent / "dashboard" / "index.html"
    if not dashboard_path.is_file():
        return None
    _dashboard_html_cache = dashboard_path.read_text(encoding="utf-8")
    return _dashboard_html_cache
