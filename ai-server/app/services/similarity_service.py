"""
FishDex AI Server - Similarity Service
=========================================
Step 4 of the pipeline: compare cropped frames of a new fish
against stored frames of existing fish profiles.

Current implementation: HSV histogram correlation (cv2.compareHist).
Future: replace with Mehdi's embedding-based cosine similarity.
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SimilarityService:
    """Compare fish images using histogram-based similarity (placeholder for future embeddings)."""

    def __init__(self) -> None:
        """Initialize. Future: load Mehdi's embedding model here."""
        self._hist_method = cv2.HISTCMP_CORREL  # 1.0 = identical, 0.0 = no correlation
        logger.info("SimilarityService initialized (histogram mode)")

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def compute_similarity(
        self, new_frames: list[np.ndarray], existing_images_dir: Path
    ) -> float:
        """
        Compare new cropped frames against an existing fish's stored frames.

        Computes pairwise HSV histogram correlation between every new frame
        and every stored frame, then returns the average of the per-new-frame
        best matches.

        Args:
            new_frames:          List of BGR numpy arrays (the new catch).
            existing_images_dir: Path to an existing fish's images/ folder.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        stored_frames = self._load_frames(existing_images_dir)
        if not stored_frames or not new_frames:
            return 0.0

        new_hists = [self._compute_hist(f) for f in new_frames]
        stored_hists = [self._compute_hist(f) for f in stored_frames]

        # For each new frame, find its best match among stored frames
        best_scores: list[float] = []
        for nh in new_hists:
            best = max(
                cv2.compareHist(nh, sh, self._hist_method) for sh in stored_hists
            )
            best_scores.append(max(0.0, best))  # clamp negatives

        return float(np.mean(best_scores)) if best_scores else 0.0

    def find_best_match(
        self,
        new_frames: list[np.ndarray],
        subset: list[dict],
        threshold: float = 0.70,
    ) -> tuple[Optional[str], float]:
        """
        Find the best matching fish in the comparison subset.

        Args:
            new_frames: List of cropped BGR frames of the new fish.
            subset:     List of fish profile dicts from SubsetService.
            threshold:  Minimum similarity to consider a match.

        Returns:
            (fish_id, similarity_score) if a match is found above threshold,
            (None, 0.0) otherwise.
        """
        if not subset or not new_frames:
            return None, 0.0

        best_id: Optional[str] = None
        best_score: float = 0.0

        for profile in subset:
            images_dir = profile.get("latest_images_dir")
            if images_dir is None:
                continue

            score = self.compute_similarity(new_frames, Path(images_dir))
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
    def _compute_hist(frame: np.ndarray) -> np.ndarray:
        """
        Compute a normalised HSV histogram for a BGR frame.

        Args:
            frame: BGR image as numpy array.

        Returns:
            Flattened, normalised histogram array.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv], [0, 1], None, [50, 60], [0, 180, 0, 256]
        )
        cv2.normalize(hist, hist)
        return hist

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
