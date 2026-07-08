"""
FishDex AI Server - Main Application
=========================================
FastAPI entry point with CORS, logging, and startup hooks.
Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import identify

# ─── Logging Configuration ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("fishdex")


# ─── Startup / Shutdown lifecycle ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before serving and cleanup on shutdown."""
    # Ensure server-data directory exists
    Path(settings.server_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info("server-data directory ready: %s", settings.server_data_dir)

    # Pre-load ONNX crop model so first request is fast
    try:
        from app.services.crop_service import get_crop_service
        crop = get_crop_service()
        logger.info("ONNX crop model loaded: %s (available=%s)", settings.onnx_model_path, crop.available)
    except Exception as exc:
        logger.warning("Could not pre-load ONNX model: %s", exc)

    logger.info(
        "═══ FishDex AI Server v2.0.0 started ═══  "
        "threshold=%.2f  radius=%.1fkm  data=%s",
        settings.similarity_threshold,
        settings.nearby_area_radius_km,
        settings.server_data_dir,
    )

    yield  # ← app is running

    logger.info("═══ FishDex AI Server shutting down ═══")


# ─── Create FastAPI app ──────────────────────────────────────────────────
app = FastAPI(
    title="FishDex AI Server",
    description="Fish identification API with 7-step pipeline for the FishDex app",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow ALL origins so the phone app can connect from any IP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register router
app.include_router(identify.router, prefix="/api/v1", tags=["Identification"])


# ─── Root endpoints ─────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check() -> dict:
    """
    Quick health check for Docker / load balancers.
    For detailed info use /api/v1/health/detailed.
    """
    try:
        from app.services.crop_service import get_crop_service
        model_loaded = get_crop_service().available
    except Exception:
        model_loaded = False

    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": "2.0.0",
        "model_loaded": model_loaded,
    }


@app.get("/", tags=["System"])
async def root() -> dict:
    """Root endpoint with service info."""
    return {
        "service": "FishDex AI Server",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }
