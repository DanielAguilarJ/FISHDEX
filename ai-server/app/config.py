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
    # Two-level geographic search for ReID
    reid_auto_match_radius_km: float = 5.0   # Within this: auto_match eligible
    reid_review_search_radius_km: float = 50.0  # Within this: review-only candidates

    # ── Detector output layout ───────────────────────────────────────
    # Ultralytics YOLOv8 OBB nc=1: [cx, cy, w, h, conf, angle]  → "xywh_conf_angle"
    # Alternative (older exports): [cx, cy, w, h, angle, conf]  → "xywh_angle_conf"
    # Override with FISHDEX_DETECTOR_OUTPUT_LAYOUT=xywh_angle_conf if needed.
    detector_output_layout: str = "xywh_conf_angle"
    detector_nms_iou_threshold: float = 0.45

    # ── Video/Frame processing ───────────────────────────────────────
    max_frames_to_save: int = 8
    max_frames_to_extract: int = 15
    max_video_size_mb: int = 50
    max_video_duration_seconds: int = 15
    jpeg_quality: int = 90
    # Max pixel dimension (longest side) for extracted frames.
    # Preserves aspect ratio; does NOT force landscape. Override: FISHDEX_FRAME_MAX_SIDE
    frame_max_side: int = 960
    # Padding fraction added around every fish crop (0.01 = 1% per side).
    # Override: FISHDEX_CROP_PADDING_FRAC
    crop_padding_frac: float = 0.01

    # ── Storage directories ──────────────────────────────────────────
    server_data_dir: str = "data"
    temp_dir: str = "data/temp"
    cache_dir: str = "data/cache"
    embeddings_db_path: str = "data/embeddings/fishdex_embeddings.sqlite"
    private_data_dir: str = "data/private"
    fish_documents_dir: str = "data/private/fish_documents"
    fish_media_dir: str = "data/storage/fish_media"
    job_artifacts_dir: str = "data/storage/jobs"

    # ── Legacy: ONNX model (kept for backward compat with old crop_service)
    onnx_model_path: str = "norway fish/fin_detector_best.onnx"

    # ── New OBB ROI detector ─────────────────────────────────────────
    # Override: FISHDEX_OBB_MODEL_PATH, FISHDEX_OBB_CONF_THRESHOLD, etc.
    obb_model_path: str = "models/detector/obb_best.pt"
    obb_conf_threshold: float = 0.35
    roi_require_single_detection: bool = True
    roi_allow_center_fallback: bool = False
    roi_min_side_px: int = 48  # Mínimo lado (px) del ROI — rechaza detecciones diminutas

    # ── New Fish ReID model ──────────────────────────────────────────
    # Override: FISHDEX_REID_MODEL_PATH, FISHDEX_REID_MODEL_NAME, etc.
    reid_model_path: str = "models/reid/reid_best.pt"
    reid_model_name: str = "convnext_small.fb_in22k_ft_in1k"
    reid_embedding_dim: int = 512
    reid_img_size: int = 128
    reid_batch_size: int = 64
    reid_num_workers: int = 0
    reid_flip_tta: bool = True  # Test-time augmentation: media(embedding original + espejo horizontal)

    # ── Prototype matching settings ──────────────────────────────────
    reid_max_support_images_per_identity: int = 12  # más soporte = prototipo estable
    reid_max_query_images_for_vote: int = 8          # más votos = decisión robusta
    reid_random_seed: int = 1234
    # Conservative threshold: false positive (wrong recapture) is worse than
    # false negative (missed recapture). 0.82 es punto de partida para trucha arcoíris.
    # Calibrar con calibrate_threshold.py antes de producción real.
    reid_similarity_threshold: float = 0.82
    reid_min_margin: float = 0.05  # Margen mínimo entre 1º y 2º candidato
    reid_cache_name: str = "fishencoder_convnext_small_512_128_v2"  # v2 = nueva caché tras flip TTA
    reid_calibration_path: str = ""  # Path to calibration JSON (empty = uncalibrated)

    # ── ReID fingerprint crop ───────────────────────────────────────────
    # Extracts the spot/pattern region from the complete deskewed ROI.
    # Default False for safe backward-compatible deployment.
    # Activate ONLY after rebuilding the embedding index.
    reid_fingerprint_crop_enabled: bool = False
    reid_fingerprint_x_start: float = 0.20
    reid_fingerprint_x_end: float = 0.80
    reid_fingerprint_y_start: float = 0.05
    reid_fingerprint_y_end: float = 0.55

    # ── Multiframe selection ─────────────────────────────────────────
    reid_min_selected_frame_gap_seconds: float = 0.30  # Temporal NMS between top-N candidates
    reid_max_selected_candidates: int = 5               # Max frames for multiframe voting

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
