"""
FishDex AI Server - Similarity Service (ReID prototype top-N voting)
=====================================================================
Reemplaza el enfoque ResNet50 promedio-vs-promedio por:

  1. Construir un prototipo L2-normalizado por fish_id a partir de:
       - Todas las carpetas image_dirs del perfil (todos los catches)
       - Máximo settings.reid_max_support_images_per_identity imágenes soporte
       - Usando *_embeddings.npy cacheados si existen (mucho más rápido)
  2. Cada frame query vota por el prototipo más cercano (cosine similarity)
  3. En caso de empate, gana quien tenga mayor similitud media
  4. average_similarity = mean(similitudes al prototipo ganador)
  5. Si average_similarity >= threshold → recaptura; si no → None

Devuelve SimilarityMatchResult (dataclass) con todos los detalles del voto,
para que inference.py pueda incluirlos en la respuesta sin acceder a estado
interno del servicio.
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Supported image extensions for loading frames from disk
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


# ---------------------------------------------------------------------------
# Result dataclass (returned by find_best_match)
# ---------------------------------------------------------------------------

@dataclass
class SimilarityMatchResult:
    """Full details of a prototype top-N vote matching round."""
    fish_id: Optional[str]           # winning fish_id if above threshold, else None
    score: float                     # average cosine similarity to winning prototype
    query_images_used: int           # number of query frames used in voting
    winning_votes: int               # votes the winner got
    candidate_count: int             # number of prototypes in the gallery
    winning_identity: Optional[str]  # always set (even when below threshold)
    margin: float = 0.0              # gap between winner and 2nd best candidate mean scores
    second_best_score: float = 0.0   # mean score of 2nd best candidate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_frame_paths_from_dirs(image_dirs: list[Path]) -> list[str]:
    """Collect all supported image file paths from a list of directories."""
    paths: list[str] = []
    for d in image_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS:
                # Skip cached .npy-named files that are not images
                paths.append(str(p))
    return paths


def _sample_paths(paths: list[str], maximum: int, rng: random.Random) -> list[str]:
    """Return up to `maximum` paths, deterministically sampled."""
    if len(paths) <= maximum:
        return list(paths)
    return sorted(rng.sample(paths, maximum))


def _load_cache_embeddings(images_dir: Path) -> Optional[np.ndarray]:
    """
    Try to load pre-computed FishEncoder embeddings from cache.

    Looks for: {reid_cache_name}_embeddings.npy
    Returns (N,512) float32 or None if not found / unreadable.
    """
    cache_path = images_dir / f"{settings.reid_cache_name}_embeddings.npy"
    if cache_path.is_file():
        try:
            arr = np.load(str(cache_path)).astype(np.float32)
            if arr.ndim == 2 and arr.shape[1] == settings.reid_embedding_dim:
                return arr
            logger.warning(
                "Cache shape mismatch at %s: %s (expected (*,%d))",
                cache_path, arr.shape, settings.reid_embedding_dim,
            )
        except Exception as exc:
            logger.warning("Failed to load embedding cache %s: %s", cache_path, exc)
    return None


def _compute_and_cache_embeddings(images_dir: Path, frames: list[np.ndarray]) -> np.ndarray:
    """
    Extract embeddings from frames using ReIDEmbeddingService and save cache.

    Returns (N,512) float32.
    """
    from app.services.reid_embedding_service import get_reid_embedding_service
    reid = get_reid_embedding_service()
    matrix = reid.extract_embedding_matrix(frames)

    # Save cache for next time
    cache_path = images_dir / f"{settings.reid_cache_name}_embeddings.npy"
    try:
        np.save(str(cache_path), matrix)
        logger.debug("Saved embedding cache: %s (%s rows)", cache_path, len(matrix))
    except Exception as exc:
        logger.warning("Could not save embedding cache %s: %s", cache_path, exc)

    return matrix


def _load_frames_from_dir(images_dir: Path) -> list[np.ndarray]:
    """Load all supported images from a directory as BGR numpy arrays."""
    frames: list[np.ndarray] = []
    if not images_dir.is_dir():
        return frames
    for p in sorted(images_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS:
            img = cv2.imread(str(p))
            if img is not None:
                frames.append(img)
    return frames


def _get_embeddings_for_dir(images_dir: Path) -> Optional[np.ndarray]:
    """
    Get embeddings for a single images/ directory.

    Priority:
      1. Load from *_embeddings.npy cache (fast)
      2. Extract from images and save cache (slow, first time)

    Returns (N,512) float32 or None if no images found.
    """
    # Try cache first
    cached = _load_cache_embeddings(images_dir)
    if cached is not None and len(cached) > 0:
        return cached

    # Fall back to loading images
    frames = _load_frames_from_dir(images_dir)
    if not frames:
        return None

    matrix = _compute_and_cache_embeddings(images_dir, frames)
    return matrix if len(matrix) > 0 else None


def _build_prototype_for_profile(
    profile: dict,
    max_support_images: int,
    rng: random.Random,
) -> Optional[np.ndarray]:
    """
    Build a normalized mean prototype for a single fish profile.

    Uses all available image_dirs (all catches), loads/computes embeddings,
    samples up to max_support_images rows, then normalizes the mean.

    Returns (512,) float32 or None if no embeddings available.
    """
    image_dirs: list[Path] = profile.get("image_dirs", [])

    # Fallback: if image_dirs missing (old subset format), use latest_images_dir
    if not image_dirs:
        latest = profile.get("latest_images_dir")
        if latest is not None:
            image_dirs = [Path(latest)]

    all_matrices: list[np.ndarray] = []
    for d in image_dirs:
        matrix = _get_embeddings_for_dir(d)
        if matrix is not None:
            all_matrices.append(matrix)

    if not all_matrices:
        return None

    # Concatenate all embeddings across catches, then sample
    full_matrix = np.concatenate(all_matrices, axis=0)  # (total_imgs, 512)

    if len(full_matrix) > max_support_images:
        indices = sorted(rng.sample(range(len(full_matrix)), max_support_images))
        full_matrix = full_matrix[indices]

    # Normalize per-row (should already be, but defensive re-normalise)
    norms = np.linalg.norm(full_matrix, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    full_matrix = full_matrix / norms

    # Mean prototype → L2-normalise
    mean_emb = full_matrix.mean(axis=0)
    norm = np.linalg.norm(mean_emb)
    if norm > 0:
        mean_emb = mean_emb / norm
    return mean_emb.astype(np.float32)


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class SimilarityService:
    """
    Fish identity matching using FishEncoder prototypes and top-N voting.

    Gallery: one L2-normalised prototype per known fish_id.
    Query:   up to reid_max_query_images_for_vote frames, each votes for
             its nearest prototype.
    Winner:  most votes; ties broken by highest mean similarity.
    """

    def __init__(self) -> None:
        logger.info(
            "SimilarityService initialized (fishencoder_prototype_topN_vote mode)  "
            "threshold=%.2f  max_support=%d  max_query=%d",
            settings.reid_similarity_threshold,
            settings.reid_max_support_images_per_identity,
            settings.reid_max_query_images_for_vote,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_best_match(
        self,
        new_frames: list[np.ndarray],
        subset: list[dict],
        threshold: float = 0.75,
    ) -> SimilarityMatchResult:
        """
        Identify the best matching fish using prototype top-N voting.

        Args:
            new_frames: List of BGR ROI frames (already OBB-cropped).
            subset:     Fish profile dicts from SubsetService.
                        Each dict must have 'fish_id' and 'image_dirs'.
            threshold:  Minimum average cosine similarity to accept a match.

        Returns:
            SimilarityMatchResult with full voting details.
            fish_id is None if best score is below threshold.
        """
        empty = SimilarityMatchResult(
            fish_id=None,
            score=0.0,
            query_images_used=0,
            winning_votes=0,
            candidate_count=0,
            winning_identity=None,
            margin=0.0,
            second_best_score=0.0,
        )

        if not subset or not new_frames:
            return empty

        rng = random.Random(settings.reid_random_seed)

        # ── Build prototype gallery ──────────────────────────────────
        prototype_list: list[np.ndarray] = []
        prototype_names: list[str] = []

        for profile in subset:
            fish_id = profile.get("fish_id")
            if not fish_id:
                continue
            proto = _build_prototype_for_profile(
                profile,
                max_support_images=settings.reid_max_support_images_per_identity,
                rng=rng,
            )
            if proto is not None:
                prototype_list.append(proto)
                prototype_names.append(fish_id)

        if not prototype_list:
            logger.info("SimilarityService: no prototypes could be built from subset")
            return empty

        prototype_matrix = np.stack(prototype_list, axis=0)  # (K, 512)
        candidate_count = len(prototype_names)

        # ── Sample query frames ──────────────────────────────────────
        max_query = settings.reid_max_query_images_for_vote
        if len(new_frames) > max_query:
            query_frames = sorted(
                rng.sample(range(len(new_frames)), max_query)
            )
            sampled_frames = [new_frames[i] for i in query_frames]
        else:
            sampled_frames = list(new_frames)

        query_images_used = len(sampled_frames)

        # ── Extract query embeddings ─────────────────────────────────
        try:
            from app.services.reid_embedding_service import get_reid_embedding_service
            reid = get_reid_embedding_service()
            query_matrix = reid.extract_embedding_matrix(sampled_frames)  # (Q, 512)
        except Exception as exc:
            logger.error("SimilarityService: ReID extraction failed: %s", exc, exc_info=True)
            return empty

        if len(query_matrix) == 0:
            return empty

        # ── Cosine similarity matrix ─────────────────────────────────
        # Both matrices are already L2-normalised → dot product = cosine sim
        similarities = query_matrix @ prototype_matrix.T  # (Q, K)

        # ── Per-image voting ─────────────────────────────────────────
        per_image_winners = similarities.argmax(axis=1)  # (Q,)
        vote_counts = Counter(per_image_winners.tolist())
        maximum_votes = max(vote_counts.values())
        tied_indices = [idx for idx, cnt in vote_counts.items() if cnt == maximum_votes]

        if len(tied_indices) == 1:
            winning_index = tied_indices[0]
        else:
            # Break tie by highest mean similarity across all query images
            winning_index = max(
                tied_indices,
                key=lambda idx: float(similarities[:, idx].mean()),
            )

        average_similarity = float(similarities[:, winning_index].mean())
        winning_identity = prototype_names[winning_index]
        winning_votes = vote_counts[winning_index]

        # ── Margen de rechazo RELATIVO AL GANADOR (por votos) ────────────
        # El ganador se decide por votos; el margen debe medir cuánto
        # destaca ESE ganador frente a su competidor más cercano, no el
        # ganador global por media. Por eso comparamos winner_mean contra
        # el mejor prototipo DISTINTO del ganador.
        mean_sims = similarities.mean(axis=0)              # (K,) media por prototipo
        winner_mean = float(mean_sims[winning_index])
        others = np.delete(mean_sims, winning_index)       # excluye al ganador
        second_best = float(others.max()) if others.size > 0 else 0.0
        match_margin = winner_mean - second_best

        logger.info(
            "SimilarityService: winner=%s  score=%.4f  votes=%d/%d  "
            "candidates=%d  query_imgs=%d  margin=%.4f  2nd_best=%.4f",
            winning_identity,
            average_similarity,
            winning_votes,
            query_images_used,
            candidate_count,
            query_images_used,
            match_margin,
            second_best,
        )

        # ── Threshold + margen de rechazo ────────────────────────────────────
        min_margin = getattr(settings, "reid_min_margin", 0.05)
        passes_threshold = average_similarity >= threshold
        # Con 1 solo candidato no tiene sentido exigir margen (no hay 2º).
        passes_margin = (candidate_count < 2) or (match_margin >= min_margin)
        matched_fish_id = winning_identity if (passes_threshold and passes_margin) else None

        if passes_threshold and not passes_margin:
            logger.info(
                "SimilarityService: REJECTED by margin — score=%.4f but margin=%.4f < %.4f "
                "(ambiguous: treating as NEW fish)",
                average_similarity, match_margin, min_margin,
            )

        return SimilarityMatchResult(
            fish_id=matched_fish_id,
            score=average_similarity,
            query_images_used=query_images_used,
            winning_votes=winning_votes,
            candidate_count=candidate_count,
            winning_identity=winning_identity,
            margin=match_margin,
            second_best_score=second_best,
        )


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
