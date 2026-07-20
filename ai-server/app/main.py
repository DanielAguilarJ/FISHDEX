"""
FishDex AI Server - Main Application
=========================================
FastAPI entry point with CORS, logging, and startup hooks.
Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.middleware.correlation import CorrelationFilter, CorrelationMiddleware
from app.routers import identify, jobs, websocket, dashboard, auth, sightings
from app.services.event_bus import EventBusLogHandler
from app.services.system_monitor import start_system_monitor
from app.services.retry_service import start_retry_service
from app.database import init_db
from fastapi.staticfiles import StaticFiles

# ─── Logging Configuration ───────────────────────────────────────────────
# Use a custom LogRecord factory to ensure 'correlation_id' is always present
# and prevent KeyError crashes during internal uvicorn/fastapi logging
old_factory = logging.getLogRecordFactory()
def record_factory(*args, **kwargs):
    record = old_factory(*args, **kwargs)
    record.correlation_id = "-"
    return record
logging.setLogRecordFactory(record_factory)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(correlation_id)s]  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Add CorrelationFilter to the root logger so all loggers inherit it
_correlation_filter = CorrelationFilter()
logging.getLogger().addFilter(_correlation_filter)

# Add EventBusLogHandler to root logger to stream logs to dashboard
_event_bus_handler = EventBusLogHandler()
_event_bus_handler.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    "%Y-%m-%d %H:%M:%S"
))
logging.getLogger().addHandler(_event_bus_handler)

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


# ─── Startup / Shutdown lifecycle ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before serving and cleanup on shutdown."""
    global _server_start_time
    _server_start_time = time.time()

    # Start background system monitoring
    start_system_monitor()

    # Start background crop retry service
    start_retry_service()

    # Initialize SQLite database
    init_db()

    # Ensure data directories exist
    Path(settings.server_data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.embeddings_db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.private_data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.fish_documents_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.fish_media_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.job_artifacts_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Data directories ready: %s", settings.server_data_dir)

    # Pre-load ONNX crop model (legacy)
    try:
        from app.services.crop_service import get_crop_service
        crop = get_crop_service()
        logger.info("Legacy ONNX crop model: available=%s", crop.available)
    except Exception as exc:
        logger.warning("Could not pre-load legacy ONNX model: %s", exc)

    # Pre-load new OBB detector (v2)
    try:
        from app.services.detector_service import get_detector_service
        detector = get_detector_service()
        logger.info("OBB Detector model: available=%s", detector.available)
    except Exception as exc:
        logger.warning("Could not pre-load OBB detector: %s", exc)

    # Pre-load species classifier
    try:
        from app.services.classifier_service import get_classifier_service
        classifier = get_classifier_service()
        logger.info("Species classifier model: available=%s", classifier.available)
    except Exception as exc:
        logger.warning("Could not pre-load species classifier: %s", exc)

    logger.info(
        "=== FishDex AI Server v2.0.0 started ===  "
        "threshold=%.2f  radius=%.1fkm  data=%s",
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
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiter — store on app.state so routers can access it
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Correlation ID middleware (outermost — added first, runs last) ───────
app.add_middleware(CorrelationMiddleware)

# CORS — allow ALL origins so the phone app can connect from any IP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(identify.router, prefix="/api/v1", tags=["Identification"])
app.include_router(jobs.router)  # jobs.router already defines prefix="/api/v1/jobs"
app.include_router(dashboard.router)
app.include_router(websocket.router)
app.include_router(auth.router)
app.include_router(sightings.router)

# Mount local storage folder to serve frames and videos directly
storage_path = Path(settings.server_data_dir) / "storage"
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")


# ─── Root endpoints ─────────────────────────────────────────────────────
from fastapi.responses import HTMLResponse, JSONResponse


@app.get("/health/live", tags=["System"])
async def health_live() -> dict:
    """Liveness probe — only checks that the process responds."""
    return {"alive": True}


@app.get("/health/ready", tags=["System"])
async def health_ready() -> JSONResponse:
    """
    Readiness probe — verifies the full pipeline is operational.
    Returns 503 if any critical component is not ready.
    """
    checks: dict = {}
    ready = True

    # 1. Database accessible
    try:
        from app.database import get_db_connection
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        checks["db_accessible"] = True
    except Exception as e:
        checks["db_accessible"] = False
        checks["db_error"] = str(e)
        ready = False

    # 2. Migrations applied
    try:
        from app.migrations.runner import get_current_version
        from app.database import get_db_connection as _gdb
        _conn = _gdb()
        checks["db_migration_version"] = get_current_version(_conn)
        _conn.close()
    except Exception:
        checks["db_migration_version"] = 0

    # 3. Detector loaded
    try:
        from app.services.detector_service import get_detector_service
        det = get_detector_service()
        checks["detector_loaded"] = det.available
        if not det.available:
            ready = False
    except Exception:
        checks["detector_loaded"] = False
        ready = False

    # 4. FishEncoder loaded
    try:
        from app.services.reid_embedding_service import get_reid_service
        reid = get_reid_service()
        checks["reid_model_loaded"] = reid.available
        if not reid.available:
            ready = False
    except Exception:
        checks["reid_model_loaded"] = False
        ready = False

    # 5. Model fingerprint
    try:
        from app.services.model_fingerprint_service import get_model_version, get_model_fingerprint
        fp = get_model_fingerprint()
        checks["reid_model_version"] = get_model_version()
        checks["embedding_dimensions"] = fp.embedding_dim
    except Exception:
        checks["reid_model_version"] = None

    # 6. Embeddings DB
    try:
        from app.services.matching_service import get_matching_service
        ms = get_matching_service()
        with ms._connect() as econn:
            row = econn.execute("SELECT COUNT(*) FROM fish_embeddings").fetchone()
            checks["historical_embeddings"] = row[0] if row else 0
    except Exception:
        checks["historical_embeddings"] = 0

    # 7. Czech areas catalog
    try:
        from app.data.czech_areas import CZECH_AREAS
        checks["czech_areas_loaded"] = len(CZECH_AREAS)
    except Exception:
        checks["czech_areas_loaded"] = 0
        ready = False

    # 8. Configuration
    checks["match_radius_km"] = settings.nearby_area_radius_km
    checks["reid_similarity_threshold"] = settings.reid_similarity_threshold

    response = {"ready": ready, **checks}
    status_code = 200 if ready else 503
    return JSONResponse(content=response, status_code=status_code)


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """Quick health check — use /health/ready for full pipeline check."""
    increment_request_count()
    uptime_seconds = round(time.time() - _server_start_time, 1) if _server_start_time else 0.0

    try:
        from app.services.detector_service import get_detector_service
        detector_loaded = get_detector_service().available
    except Exception:
        detector_loaded = False

    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": "2.1.0",
        "uptime_seconds": uptime_seconds,
        "detector_loaded": detector_loaded,
        "request_count": _request_count,
    }


@app.get("/", tags=["System"])
async def root() -> HTMLResponse:
    """Root endpoint serving the Dashboard HTML."""
    dashboard_path = Path(__file__).parent / "dashboard" / "index.html"
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard HTML not found</h1>", status_code=404)
