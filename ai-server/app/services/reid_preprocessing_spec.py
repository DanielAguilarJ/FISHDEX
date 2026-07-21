"""
ReID Preprocessing Spec
========================
Immutable description of exactly how embeddings for a given model_version
were generated.  Binds model_version to preprocessing parameters so the
rebuild command cannot accidentally store full-fish embeddings under a
fingerprint model_version label.

Usage:
    spec = ReIDPreprocessingSpec.from_active_config()
    spec.validate_for_rebuild()   # raises RuntimeError on mismatch
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReIDPreprocessingSpec:
    """
    Immutable snapshot of all inference-relevant ReID parameters.

    This is the canonical source of truth for the rebuild command.
    If any field differs between the active config and the target
    model_version, the rebuild must refuse to run.
    """

    model_version: str
    checkpoint_sha256: str   # first 12 hex chars of reid_model_path
    model_name: str          # e.g. "convnext_small.fb_in22k_ft_in1k"
    embedding_dim: int       # 512
    img_size: int            # 128
    flip_tta: bool           # True
    fingerprint_enabled: bool
    x_start: float           # 0.20  (only meaningful if fingerprint_enabled)
    x_end: float             # 0.80
    y_start: float           # 0.05
    y_end: float             # 0.55

    @classmethod
    def from_active_config(cls) -> "ReIDPreprocessingSpec":
        """
        Build spec from current settings + model fingerprint.

        Requires the checkpoint file to exist on disk (for SHA-256).
        """
        from app.services.model_fingerprint_service import get_model_fingerprint
        from app.config import settings

        fp = get_model_fingerprint()
        return cls(
            model_version=fp.model_version,
            checkpoint_sha256=fp.checkpoint_sha256,
            model_name=settings.reid_model_name,
            embedding_dim=settings.reid_embedding_dim,
            img_size=settings.reid_img_size,
            flip_tta=settings.reid_flip_tta,
            fingerprint_enabled=settings.reid_fingerprint_crop_enabled,
            x_start=settings.reid_fingerprint_x_start if settings.reid_fingerprint_crop_enabled else 0.0,
            x_end=settings.reid_fingerprint_x_end if settings.reid_fingerprint_crop_enabled else 1.0,
            y_start=settings.reid_fingerprint_y_start if settings.reid_fingerprint_crop_enabled else 0.0,
            y_end=settings.reid_fingerprint_y_end if settings.reid_fingerprint_crop_enabled else 1.0,
        )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_for_rebuild(self) -> None:
        """
        Raise RuntimeError if the active config does not match this spec.
        Called by the rebuild command before inserting any embedding.
        """
        active = ReIDPreprocessingSpec.from_active_config()

        mismatches: list[str] = []
        for field_name in self.__dataclass_fields__:
            expected = getattr(self, field_name)
            actual = getattr(active, field_name)
            if expected != actual:
                mismatches.append(
                    f"  {field_name}: expected={expected!r}  active={actual!r}"
                )

        if mismatches:
            raise RuntimeError(
                "Preprocessing spec mismatch — cannot rebuild.\n"
                + "\n".join(mismatches)
                + "\nSet env vars to match the target spec before rebuilding."
            )

    def validate_fingerprint_consistency(self) -> None:
        """
        Raise RuntimeError if model_version implies fingerprint but config
        has fingerprint disabled, or vice versa.
        """
        version_has_fp = "_fp_" in self.model_version or "_fp-" in self.model_version

        if self.fingerprint_enabled and not version_has_fp:
            raise RuntimeError(
                f"Fingerprint is ENABLED in config but model_version "
                f"'{self.model_version}' does not contain '_fp_'. "
                f"This would produce fingerprint embeddings stored under "
                f"a full-fish model_version label."
            )

        if not self.fingerprint_enabled and version_has_fp:
            raise RuntimeError(
                f"Fingerprint is DISABLED in config but model_version "
                f"'{self.model_version}' contains '_fp_'. "
                f"This would produce full-fish embeddings stored under "
                f"a fingerprint model_version label."
            )

    def validate_reid_service_loaded(self) -> None:
        """Raise RuntimeError if the ReID embedding service is not loaded."""
        from app.services.reid_embedding_service import get_reid_embedding_service

        reid = get_reid_embedding_service()
        if not reid.is_loaded:
            raise RuntimeError(
                "ReIDEmbeddingService is not loaded. "
                "Cannot generate embeddings. Check FISHDEX_REID_MODEL_PATH."
            )

    def full_validation(self) -> None:
        """Run all validations required before rebuild --execute."""
        self.validate_for_rebuild()
        self.validate_fingerprint_consistency()
        self.validate_reid_service_loaded()

    def to_dict(self) -> dict:
        """Serialize to dict for logging and JSON output."""
        return {
            "model_version": self.model_version,
            "checkpoint_sha256": self.checkpoint_sha256,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "img_size": self.img_size,
            "flip_tta": self.flip_tta,
            "fingerprint_enabled": self.fingerprint_enabled,
            "x_start": self.x_start,
            "x_end": self.x_end,
            "y_start": self.y_start,
            "y_end": self.y_end,
        }
