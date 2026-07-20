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
        self.path = path
        super().__init__(f"ReID checkpoint not found: {path}")


# ── Data Model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelFingerprint:
    checkpoint_sha256: str  # first 12 hex chars
    model_name: str
    embedding_dim: int
    image_size: int
    preprocessing_version: str
    tta_version: str
    crop_version: str
    normalization_version: str

    @property
    def model_name_short(self) -> str:
        """Shorten timm-style model name for the version string.

        'convnext_small.fb_in22k_ft_in1k' -> 'convnext-small'
        """
        base = self.model_name.split(".")[0]
        return base.replace("_", "-")

    @property
    def model_version(self) -> str:
        """Deterministic version string encoding all inference-relevant params.

        Format:
            fishencoder:<sha256-12>:<model_short>:<dim>:<img_size>:<prep>:<tta>:<crop>
        """
        return ":".join([
            "fishencoder",
            self.checkpoint_sha256,
            self.model_name_short,
            str(self.embedding_dim),
            str(self.image_size),
            self.preprocessing_version,
            self.tta_version,
            self.crop_version,
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

    fingerprint = ModelFingerprint(
        checkpoint_sha256=sha_short,
        model_name=settings.reid_model_name,
        embedding_dim=settings.reid_embedding_dim,
        image_size=settings.reid_img_size,
        preprocessing_version="prep1",
        tta_version=tta_version,
        crop_version="crop1",
        normalization_version="l2_v1",
    )

    _cached_fingerprint = fingerprint

    logger.info(
        "Model fingerprint computed: version=%s sha=%s dim=%d img=%d tta=%s",
        fingerprint.model_version,
        fingerprint.checkpoint_sha256,
        fingerprint.embedding_dim,
        fingerprint.image_size,
        fingerprint.tta_version,
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
