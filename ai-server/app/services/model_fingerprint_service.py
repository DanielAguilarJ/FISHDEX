"""
Model Fingerprint Service
==========================
Computes a deterministic fingerprint of the active ReID model at startup.
Used to version embeddings and detect index/model mismatches.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────


class ModelNotAvailableError(Exception):
    """Raised when the ReID checkpoint file does not exist on disk."""

    def __init__(self, path: Path) -> None:
        """Initialise the fingerprint cache."""
        self.path = path
        super().__init__(f"ReID checkpoint not found: {path}")


# ── Data Model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelFingerprint:
    """Identifies the exact model and preprocessing that produced an embedding."""
    checkpoint_sha256: str  # first 12 hex chars
    model_name: str
    embedding_dim: int
    image_size: int
    preprocessing_version: str
    tta_version: str
    crop_version: str
    normalization_version: str
    fingerprint_enabled: bool = False
    fingerprint_x_start: float = 0.0
    fingerprint_x_end: float = 1.0
    fingerprint_y_start: float = 0.0
    fingerprint_y_end: float = 1.0

    @property
    def model_name_short(self) -> str:
        """Shorten timm-style model name for the version string.

        'convnext_small.fb_in22k_ft_in1k' -> 'convnext-small'
        """
        base = self.model_name.split(".")[0]
        return base.replace("_", "-")

    @property
    def fingerprint_crop_version(self) -> str:
        """Encode fingerprint crop params in a Windows-safe filename token.

        Examples:
            fingerprint disabled -> "full"
            x=0.20-0.80 y=0.05-0.55 -> "fp_x020_080_y005_055"
        """
        if not self.fingerprint_enabled:
            return "full"
        x0 = int(round(self.fingerprint_x_start * 100))
        x1 = int(round(self.fingerprint_x_end * 100))
        y0 = int(round(self.fingerprint_y_start * 100))
        y1 = int(round(self.fingerprint_y_end * 100))
        return f"fp_x{x0:03d}_{x1:03d}_y{y0:03d}_{y1:03d}"

    @property
    def model_version(self) -> str:
        """Deterministic version string encoding all inference-relevant params.

        Format (Windows-safe, uses underscores only):
            fishencoder_<sha12>_<model_short>_<dim>_<img>_<tta>_<crop>

        Examples:
            fishencoder_abc123def456_convnext-small_512_128_flip1_full
            fishencoder_abc123def456_convnext-small_512_128_flip1_fp_x020_080_y005_055
        """
        return "_".join([
            "fishencoder",
            self.checkpoint_sha256,
            self.model_name_short,
            str(self.embedding_dim),
            str(self.image_size),
            self.tta_version,
            self.fingerprint_crop_version,
        ])


# ── Core Functions ────────────────────────────────────────────────────────────


def compute_checkpoint_sha256(path: Path) -> str:
    """Compute SHA-256 of the checkpoint file and return first 12 hex chars.

    Reads the full file (streaming in 8MB chunks to keep memory bounded).
    Raises ModelNotAvailableError if the file doesn't exist.
    """
    if not path.exists():
        raise ModelNotAvailableError(path)

    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):  # 8MB chunks
            sha256.update(chunk)

    return sha256.hexdigest()[:12]


# ── Singleton Cache ───────────────────────────────────────────────────────────

_cached_fingerprint: Optional[ModelFingerprint] = None


def get_model_fingerprint() -> ModelFingerprint:
    """Return the cached ModelFingerprint, computing it on first call.

    Raises ModelNotAvailableError if the checkpoint is missing.
    """
    global _cached_fingerprint

    if _cached_fingerprint is not None:
        return _cached_fingerprint

    checkpoint_path = Path(settings.reid_model_path)
    sha_short = compute_checkpoint_sha256(checkpoint_path)

    tta_version = "flip1" if settings.reid_flip_tta else "none"

    fp_enabled = settings.reid_fingerprint_crop_enabled

    fingerprint = ModelFingerprint(
        checkpoint_sha256=sha_short,
        model_name=settings.reid_model_name,
        embedding_dim=settings.reid_embedding_dim,
        image_size=settings.reid_img_size,
        preprocessing_version="prep1",
        tta_version=tta_version,
        crop_version=(
            "fp_x{:03d}_{:03d}_y{:03d}_{:03d}".format(
                int(round(settings.reid_fingerprint_x_start * 100)),
                int(round(settings.reid_fingerprint_x_end * 100)),
                int(round(settings.reid_fingerprint_y_start * 100)),
                int(round(settings.reid_fingerprint_y_end * 100)),
            )
            if fp_enabled
            else "full"
        ),
        normalization_version="l2_v1",
        fingerprint_enabled=fp_enabled,
        fingerprint_x_start=settings.reid_fingerprint_x_start if fp_enabled else 0.0,
        fingerprint_x_end=settings.reid_fingerprint_x_end if fp_enabled else 1.0,
        fingerprint_y_start=settings.reid_fingerprint_y_start if fp_enabled else 0.0,
        fingerprint_y_end=settings.reid_fingerprint_y_end if fp_enabled else 1.0,
    )

    _cached_fingerprint = fingerprint

    logger.info(
        "Model fingerprint computed: version=%s sha=%s dim=%d img=%d "
        "tta=%s fingerprint=%s crop_version=%s",
        fingerprint.model_version,
        fingerprint.checkpoint_sha256,
        fingerprint.embedding_dim,
        fingerprint.image_size,
        fingerprint.tta_version,
        fingerprint.fingerprint_enabled,
        fingerprint.fingerprint_crop_version,
    )

    return fingerprint


def get_model_version() -> str:
    """Return the derived model version string."""
    return get_model_fingerprint().model_version


def validate_fingerprint_matches_index(index_version: str) -> bool:
    """Check whether the current model version matches an index's stored version.

    Args:
        index_version: The version string stored in an embedding index/database.

    Returns:
        True if the current model version matches exactly, False otherwise.
    """
    return get_model_version() == index_version
