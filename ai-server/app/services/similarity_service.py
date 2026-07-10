"""
FishDex AI Server - Similarity Service
=========================================
Step 4 of the pipeline: compare cropped frames of a new fish
against stored frames of existing fish profiles.

Implementation: ResNet50 embeddings + cosine similarity.
Pre-computed embeddings are loaded from .npy files when available,
avoiding redundant extraction on every comparison.
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class SimilarityService:
    """Compare fish images using ResNet50 embedding cosine similarity."""

    def __init__(self) -> None:
        """Initialize. The EmbeddingService is accessed via its singleton."""
        self._emb_service = get_embedding_service()
        logger.info("SimilarityService initialized (resnet50_cosine mode)")

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def compute_similarity(
        self, new_frames: list[np.ndarray], existing_images_dir: Path
    ) -> float:
        """
        Compare new cropped frames against an existing fish's stored frames.

        If a pre-computed embeddings.npy exists in existing_images_dir, it is
        loaded directly.  Otherwise, stored frames are loaded and their
        embedding is computed on the fly.

        Args:
            new_frames:          List of BGR numpy arrays (the new catch).
            existing_images_dir: Path to an existing fish's images/ folder.

        Returns:
            Cosine similarity score between 0.0 and 1.0.
        """
        if not new_frames:
            return 0.0

        # Compute embedding for the new catch
        new_embedding = self._emb_service.extract_embeddings(new_frames)

        # Try to load pre-computed embedding for the existing fish
        stored_embedding = self._load_embedding(existing_images_dir)
        if stored_embedding is None:
            # Fall back to extracting from stored frames
            stored_frames = self._load_frames(existing_images_dir)
            if not stored_frames:
                return 0.0
            stored_embedding = self._emb_service.extract_embeddings(stored_frames)

        return self._emb_service.compute_cosine_similarity(new_embedding, stored_embedding)

    def find_best_match(
        self,
        new_frames: list[np.ndarray],
        subset: list[dict],
        threshold: float = 0.60,
    ) -> tuple[Optional[str], float]:
        """
        Find the best matching fish in the comparison subset.

        Args:
            new_frames: List of cropped BGR frames of the new fish.
            subset:     List of fish profile dicts from SubsetService.
            threshold:  Minimum cosine similarity to consider a match.

        Returns:
            (fish_id, similarity_score) if a match is found above threshold,
            (None, 0.0) otherwise.
        """
        if not subset or not new_frames:
            return None, 0.0

        # Pre-compute embedding for the new catch once
        new_embedding = self._emb_service.extract_embeddings(new_frames)

        best_id: Optional[str] = None
        best_score: float = 0.0

        for profile in subset:
            images_dir = profile.get("latest_images_dir")
            if images_dir is None:
                continue

            images_dir = Path(images_dir)

            # Try pre-computed embedding, fall back to frame extraction
            stored_embedding = self._load_embedding(images_dir)
            if stored_embedding is None:
                stored_frames = self._load_frames(images_dir)
                if not stored_frames:
                    continue
                stored_embedding = self._emb_service.extract_embeddings(stored_frames)

            score = self._emb_service.compute_cosine_similarity(
                new_embedding, stored_embedding
            )
            logger.debug(
                "Similarity %s vs %s: %.4f", "new_fish", profile["fish_id"], score
            )

            if score > best_score:
                best_score = score
                best_id = profile["fish_id"]

        if best_score >= threshold and best_id is not None:
            logger.info("Match found: %s (score=%.4f)", best_id, best_score)
            return best_id, best_score

        logger.info("No match above threshold %.2f (best=%.4f)", threshold, best_score)
        return None, best_score

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_embedding(images_dir: Path) -> Optional[np.ndarray]:
        """
        Load a pre-computed embedding from images_dir/embeddings.npy.

        Args:
            images_dir: Path to the images/ folder.

        Returns:
            2048-d numpy vector if file exists, None otherwise.
        """
        emb_path = images_dir / "embeddings.npy"
        if emb_path.is_file():
            try:
                embedding = np.load(str(emb_path))
                return embedding.astype(np.float32)
            except Exception as exc:
                logger.warning("Failed to load %s: %s", emb_path, exc)
        return None

    @staticmethod
    def _load_frames(images_dir: Path) -> list[np.ndarray]:
        """
        Load all JPEG frames from an images/ directory.

        Args:
            images_dir: Path to the images/ folder.

        Returns:
            List of BGR numpy arrays.
        """
        frames: list[np.ndarray] = []
        if not images_dir.is_dir():
            return frames

        for img_path in sorted(images_dir.glob("frame_*.jpg")):
            img = cv2.imread(str(img_path))
            if img is not None:
                frames.append(img)

        return frames


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_similarity_service: Optional[SimilarityService] = None


def get_similarity_service() -> SimilarityService:
    """Get or create the singleton SimilarityService instance."""
    global _similarity_service
    if _similarity_service is None:
        _similarity_service = SimilarityService()
    return _similarity_service
