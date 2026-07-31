"""
FishDex AI Server - Configuration
=================================
Centralized settings using pydantic-settings.

Override any setting with an environment variable prefixed ``FISHDEX_``, e.g.
``FISHDEX_SIMILARITY_THRESHOLD=0.80``.

Every probability-like setting is range-validated (``0.0 <= x <= 1.0``) so a
typo such as ``FISHDEX_REID_SIMILARITY_THRESHOLD=82`` fails fast at startup
instead of silently disabling all matching.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Single source of truth for the version reported by every health endpoint.
SERVICE_VERSION = "2.2.0"

_PLACEHOLDER_SECRETS = frozenset({"change-me", "change-me-in-production", ""})
_VALID_ENVIRONMENTS = frozenset({"development", "staging", "production", "test"})


class Settings(BaseSettings):
    """Server configuration. Override with environment variables prefixed FISHDEX_."""

    model_config = SettingsConfigDict(
        env_prefix="FISHDEX_",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Service identity ─────────────────────────────────────────────
    service_version: str = SERVICE_VERSION

    # ── Models ───────────────────────────────────────────────────────
    detector_model_path: str = "models/detector/fish_detector_v1.onnx"
    classifier_model_path: str = "models/classifier/fish_species_v1.onnx"
    classifier_labels_path: str = "models/classifier/labels.json"
    detector_type: str = "yolov8_obb"

    # ── Detection/Classification thresholds ──────────────────────────
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    detector_confidence_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    similarity_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    nearby_area_radius_km: float = Field(default=5.0, gt=0.0, le=1000.0)
    # Two-level geographic search for ReID
    reid_auto_match_radius_km: float = Field(default=5.0, gt=0.0, le=1000.0)
    reid_review_search_radius_km: float = Field(default=50.0, gt=0.0, le=5000.0)

    # ── Detector output layout ───────────────────────────────────────
    # Ultralytics YOLOv8 OBB nc=1: [cx, cy, w, h, conf, angle]  → "xywh_conf_angle"
    # Alternative (older exports): [cx, cy, w, h, angle, conf]  → "xywh_angle_conf"
    # Override with FISHDEX_DETECTOR_OUTPUT_LAYOUT=xywh_angle_conf if needed.
    detector_output_layout: str = "xywh_conf_angle"
    detector_nms_iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)

    # ── Video/Frame processing ───────────────────────────────────────
    max_frames_to_save: int = Field(default=8, ge=1, le=128)
    max_frames_to_extract: int = Field(default=15, ge=1, le=512)
    max_video_size_mb: int = Field(default=50, ge=1, le=2048)
    max_video_duration_seconds: int = Field(default=15, ge=1, le=600)
    jpeg_quality: int = Field(default=90, ge=1, le=100)
    # Max pixel dimension (longest side) for extracted frames.
    # Preserves aspect ratio; does NOT force landscape. Override: FISHDEX_FRAME_MAX_SIDE
    frame_max_side: int = Field(default=960, ge=64, le=8192)
    # Padding fraction added around every fish crop (0.01 = 1% per side).
    # Override: FISHDEX_CROP_PADDING_FRAC
    crop_padding_frac: float = Field(default=0.01, ge=0.0, le=0.5)

    # ── Storage directories ──────────────────────────────────────────
    server_data_dir: str = "data"
    temp_dir: str = "data/temp"
    cache_dir: str = "data/cache"
    embeddings_db_path: str = "data/embeddings/fishdex_embeddings.sqlite"
    private_data_dir: str = "data/private"
    fish_documents_dir: str = "data/private/fish_documents"
    fish_media_dir: str = "data/storage/fish_media"
    job_artifacts_dir: str = "data/storage/jobs"

    # ── New OBB ROI detector ─────────────────────────────────────────
    # Override: FISHDEX_OBB_MODEL_PATH, FISHDEX_OBB_CONF_THRESHOLD, etc.
    obb_model_path: str = "models/detector/obb_best.pt"
    obb_conf_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    roi_require_single_detection: bool = True
    roi_allow_center_fallback: bool = False
    # Minimum ROI side in pixels — rejects tiny spurious detections.
    roi_min_side_px: int = Field(default=48, ge=1, le=4096)

    # ── New Fish ReID model ──────────────────────────────────────────
    # Override: FISHDEX_REID_MODEL_PATH, FISHDEX_REID_MODEL_NAME, etc.
    reid_model_path: str = "models/reid/reid_best.pt"
    reid_model_name: str = "convnext_small.fb_in22k_ft_in1k"
    reid_embedding_dim: int = Field(default=512, ge=32, le=8192)
    reid_img_size: int = Field(default=128, ge=32, le=1024)
    reid_batch_size: int = Field(default=64, ge=1, le=1024)
    reid_num_workers: int = Field(default=0, ge=0, le=64)
    # Test-time augmentation: mean(original embedding, horizontal mirror).
    reid_flip_tta: bool = True

    # ── Prototype matching settings ──────────────────────────────────
    # More support images produce a more stable prototype.
    reid_max_support_images_per_identity: int = Field(default=12, ge=1, le=256)
    # More query votes produce a more robust decision.
    reid_max_query_images_for_vote: int = Field(default=8, ge=1, le=128)
    reid_random_seed: int = 1234
    # Conservative threshold: a false positive (wrong recapture) is worse than a
    # false negative (missed recapture). Calibrate with calibrate_threshold.py
    # before real production use.
    reid_similarity_threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    # Minimum margin between the best and second-best candidate.
    reid_min_margin: float = Field(default=0.05, ge=0.0, le=1.0)
    reid_cache_name: str = "fishencoder_convnext_small_512_128_v2"
    reid_calibration_path: str = ""  # Path to calibration JSON (empty = uncalibrated)

    # ── ReID fingerprint crop ───────────────────────────────────────────
    # Extracts the spot/pattern region from the complete deskewed ROI.
    # Default False for safe backward-compatible deployment.
    # Activate ONLY after rebuilding the embedding index.
    reid_fingerprint_crop_enabled: bool = False
    reid_fingerprint_x_start: float = Field(default=0.20, ge=0.0, le=1.0)
    reid_fingerprint_x_end: float = Field(default=0.80, ge=0.0, le=1.0)
    reid_fingerprint_y_start: float = Field(default=0.05, ge=0.0, le=1.0)
    reid_fingerprint_y_end: float = Field(default=0.55, ge=0.0, le=1.0)

    # ── Multiframe selection ─────────────────────────────────────────
    # Temporal NMS between top-N candidates.
    reid_min_selected_frame_gap_seconds: float = Field(default=0.30, ge=0.0, le=60.0)
    # Max frames used for multiframe voting.
    reid_max_selected_candidates: int = Field(default=5, ge=1, le=64)

    # ── Identification result cache ──────────────────────────────────
    # Short-lived cache of completed job results, keyed by job id. Avoids
    # re-reading and re-assembling the sighting document on every poll while the
    # mobile client waits for a result.
    result_cache_enabled: bool = True
    result_cache_ttl_seconds: int = Field(default=300, ge=0, le=86_400)
    result_cache_max_entries: int = Field(default=512, ge=1, le=100_000)

    # ── Auth settings ────────────────────────────────────────────────
    skip_auth: bool = False
    ai_server_secret: str = "change-me-in-production"
    client_secret: str = "change-me"
    dashboard_secret: str = "change-me"
    environment: str = "development"
    device: str = "cpu"

    # ── CORS ─────────────────────────────────────────────────────────
    # Comma-separated list of allowed browser origins for the dashboard.
    # Native mobile clients do not enforce CORS and do not need an entry here.
    # "*" is accepted only outside production.
    cors_allowed_origins: str = "*"

    # ── Validators ───────────────────────────────────────────────────
    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        """Reject unknown environment names, which would bypass prod guards."""
        normalized = value.strip().lower()
        if normalized not in _VALID_ENVIRONMENTS:
            raise ValueError(
                f"environment must be one of {sorted(_VALID_ENVIRONMENTS)}, got {value!r}"
            )
        return normalized

    @field_validator("device")
    @classmethod
    def _validate_device(cls, value: str) -> str:
        """Accept only torch device strings the services understand."""
        normalized = value.strip().lower()
        if normalized not in {"cpu", "cuda", "mps"} and not normalized.startswith("cuda:"):
            raise ValueError(f"device must be cpu, cuda, cuda:N or mps, got {value!r}")
        return normalized

    @field_validator("reid_fingerprint_x_end")
    @classmethod
    def _validate_x_bounds(cls, value: float, info) -> float:
        """Ensure the fingerprint crop has a positive width."""
        start = info.data.get("reid_fingerprint_x_start")
        if start is not None and value <= start:
            raise ValueError(
                "reid_fingerprint_x_end must be greater than reid_fingerprint_x_start"
            )
        return value

    @field_validator("reid_fingerprint_y_end")
    @classmethod
    def _validate_y_bounds(cls, value: float, info) -> float:
        """Ensure the fingerprint crop has a positive height."""
        start = info.data.get("reid_fingerprint_y_start")
        if start is not None and value <= start:
            raise ValueError(
                "reid_fingerprint_y_end must be greater than reid_fingerprint_y_start"
            )
        return value

    # ── Derived helpers ──────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        """True when running with production guarantees enabled."""
        return self.environment == "production"

    def placeholder_secret_names(self) -> list[str]:
        """
        List secrets still set to a build-time placeholder.

        Returns:
            Field names whose value is a known placeholder such as ``change-me``.
        """
        return [
            name
            for name in ("ai_server_secret", "client_secret", "dashboard_secret")
            if getattr(self, name, "") in _PLACEHOLDER_SECRETS
        ]

    def resolved_cors_origins(self) -> list[str]:
        """
        Parse :attr:`cors_allowed_origins` into a list.

        Returns:
            The configured origins. In production a wildcard is refused and an
            empty list is returned instead, which blocks browser access rather
            than silently allowing every origin with credentials.
        """
        raw = (self.cors_allowed_origins or "").strip()
        if raw == "*":
            if self.is_production:
                logger.error(
                    "FISHDEX_CORS_ALLOWED_ORIGINS='*' is not allowed in production; "
                    "browser requests will be blocked. Set explicit origins."
                )
                return []
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


# Singleton instance — import this everywhere
settings = Settings()

# Safety check: refuse to start with skip_auth in production
if settings.skip_auth and settings.is_production:
    raise RuntimeError(
        "FATAL: FISHDEX_SKIP_AUTH=True is not allowed when "
        "FISHDEX_ENVIRONMENT=production. Fix your configuration."
    )
elif settings.skip_auth:
    logger.warning(
        "AUTH DISABLED (FISHDEX_SKIP_AUTH=True). "
        "All endpoints are unprotected. Do NOT use in production."
    )
