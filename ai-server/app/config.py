"""
FishDex AI Server - Configuration
===================================
Centralized settings using pydantic-settings.
Override any setting with environment variables prefixed FISHDEX_.
Example: FISHDEX_SIMILARITY_THRESHOLD=0.80
"""

import logging
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Server configuration. Override with environment variables prefixed FISHDEX_."""

    # ── Appwrite ─────────────────────────────────────────────────────
    appwrite_endpoint: str = "https://fra.cloud.appwrite.io/v1"
    appwrite_project_id: str = ""
    appwrite_api_key: str = ""
    appwrite_database_id: str = "fishdex_db"

    # ── Storage Buckets (all point to fish_photos on free plan) ────
    capture_raw_videos_bucket: str = "fish_photos"
    capture_frames_bucket: str = "fish_photos"
    fish_reference_images_bucket: str = "fish_photos"

    # ── Models ───────────────────────────────────────────────────────
    detector_model_path: str = "models/detector/fish_detector_v1.onnx"
    classifier_model_path: str = "models/classifier/fish_species_v1.onnx"
    classifier_labels_path: str = "models/classifier/labels.json"
    detector_type: str = "yolov8_obb"

    # ── Detection/Classification thresholds ──────────────────────────
    confidence_threshold: float = 0.70
    detector_confidence_threshold: float = 0.30
    similarity_threshold: float = 0.70
    nearby_area_radius_km: float = 5.0

    # ── Video/Frame processing ───────────────────────────────────────
    max_frames_to_save: int = 5
    max_frames_to_extract: int = 10
    max_video_size_mb: int = 50
    max_video_duration_seconds: int = 15
    jpeg_quality: int = 90

    # ── Storage directories ──────────────────────────────────────────
    server_data_dir: str = "data"
    temp_dir: str = "data/temp"
    cache_dir: str = "data/cache"
    embeddings_db_path: str = "data/embeddings/fishdex_embeddings.sqlite"

    # ── Legacy: ONNX model (kept for backward compat with old crop_service)
    onnx_model_path: str = "norway fish/fin_detector_best.onnx"

    # ── Auth settings ────────────────────────────────────────────────
    skip_auth: bool = False
    ai_server_secret: str = "change-me-in-production"
    client_secret: str = "change-me"
    dashboard_secret: str = "change-me"
    environment: str = "development"
    device: str = "cpu"

    class Config:
        env_prefix = "FISHDEX_"


# Singleton instance — import this everywhere
settings = Settings()

# Safety check: refuse to start with skip_auth in production
if settings.skip_auth and settings.environment == "production":
    raise RuntimeError(
        "FATAL: FISHDEX_SKIP_AUTH=True is not allowed when "
        "FISHDEX_ENVIRONMENT=production. Fix your configuration."
    )
elif settings.skip_auth:
    logger.warning(
        "AUTH DISABLED (FISHDEX_SKIP_AUTH=True). "
        "All endpoints are unprotected. Do NOT use in production."
    )
