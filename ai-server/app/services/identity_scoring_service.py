"""
Identity Scoring Service for FishDex.

Implements per-individual scoring with multi-frame voting:
1. Each query frame votes for its most similar candidate
2. Winner is determined by vote count, then by median score
3. Returns top-1, top-2, margin, agreement, and per-frame breakdown
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoringResult:
    """Result of identity scoring."""

    top1_fish_id: Optional[str]
    top1_score: float
    top2_fish_id: Optional[str]
    top2_score: float
    margin: float
    agreement_ratio: float
    winning_votes: int
    total_votes: int
    candidates_evaluated: int
    score_dispersion: float  # std dev of per-frame scores for winner
    per_frame_winners: list[str]  # fish_id that won each frame


def _empty_result() -> ScoringResult:
    """Return a zeroed-out result for empty gallery case."""
    return ScoringResult(
        top1_fish_id=None,
        top1_score=0.0,
        top2_fish_id=None,
        top2_score=0.0,
        margin=0.0,
        agreement_ratio=0.0,
        winning_votes=0,
        total_votes=0,
        candidates_evaluated=0,
        score_dispersion=0.0,
        per_frame_winners=[],
    )


def _validate_embeddings(arr: np.ndarray, name: str) -> None:
    """Validate that embeddings contain no NaN or Inf values."""
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains NaN or Inf values")


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    """L2-normalize rows of a 2D array."""
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)  # avoid division by zero
    return arr / norms


def score_candidates(
    query_embeddings: np.ndarray,
    candidate_gallery: dict[str, np.ndarray],
    max_support_per_identity: int = 8,
) -> ScoringResult:
    """
    Score query embeddings against a candidate gallery.

    Args:
        query_embeddings: shape (Q, D) — L2-normalized query frame embeddings
        candidate_gallery: dict mapping fish_id -> shape (S, D) support embeddings
        max_support_per_identity: max supports to use per individual (balancing)

    Returns:
        ScoringResult with full scoring breakdown

    Algorithm:
    1. For each candidate, limit support set and L2-normalize.
    2. For each query frame, compute robust score vs each candidate:
       similarities = q @ S_i.T, robust_score = median of top-k values.
    3. Each frame votes for its best candidate.
    4. Aggregate: winner by votes, then median score as tiebreak.
    5. Compute margin, agreement, dispersion.
    """
    # --- Input validation ---
    if query_embeddings.ndim != 2 or query_embeddings.shape[0] == 0:
        raise ValueError(
            "query_embeddings must be a non-empty 2D array of shape (Q, D)"
        )

    _validate_embeddings(query_embeddings, "query_embeddings")

    # Ensure L2-normalized queries
    query_embeddings = _l2_normalize(query_embeddings)

    # Handle empty gallery
    if not candidate_gallery:
        return _empty_result()

    Q, D = query_embeddings.shape
    fish_ids = list(candidate_gallery.keys())
    num_candidates = len(fish_ids)

    # --- Build per-frame x per-candidate score matrix ---
    # Shape: (Q, num_candidates)
    per_frame_scores = np.zeros((Q, num_candidates), dtype=np.float64)

    for c_idx, fish_id in enumerate(fish_ids):
        support = candidate_gallery[fish_id]

        if support.ndim != 2:
            raise ValueError(
                f"Support embeddings for '{fish_id}' must be 2D, got shape {support.shape}"
            )
        if support.shape[1] != D:
            raise ValueError(
                f"Dimension mismatch: query has D={D}, "
                f"support for '{fish_id}' has D={support.shape[1]}"
            )

        _validate_embeddings(support, f"support[{fish_id}]")

        # Limit support set size (random sample without replacement)
        S_i = support.shape[0]
        if S_i > max_support_per_identity:
            rng = np.random.default_rng(seed=hash(fish_id) & 0xFFFFFFFF)
            indices = rng.choice(S_i, size=max_support_per_identity, replace=False)
            support = support[indices]
            S_i = max_support_per_identity

        # L2-normalize support
        support = _l2_normalize(support)

        # Compute similarities: (Q, S_i) via matrix multiplication
        similarities = query_embeddings @ support.T  # (Q, S_i)

        # Robust score per frame: median of top-k similarities
        k = min(3, S_i)

        if k == S_i:
            # All values participate — median across full support
            # For k<=3, partition isn't faster; just sort the small axis
            per_frame_scores[:, c_idx] = np.median(
                np.sort(similarities, axis=1)[:, -k:], axis=1
            )
        else:
            # Partial sort to get top-k per row, then median
            # np.partition: kth smallest, so we want partition at S_i - k
            partitioned = np.partition(similarities, S_i - k, axis=1)[:, -k:]
            per_frame_scores[:, c_idx] = np.median(partitioned, axis=1)

    # --- Per-frame voting ---
    per_frame_winner_indices = np.argmax(per_frame_scores, axis=1)  # (Q,)
    per_frame_winners = [fish_ids[idx] for idx in per_frame_winner_indices]

    # --- Aggregate candidate scores (median across frames) ---
    candidate_medians = np.median(per_frame_scores, axis=0)  # (num_candidates,)

    # --- Vote counting ---
    vote_counts = np.bincount(per_frame_winner_indices, minlength=num_candidates)

    # --- Determine winner: most votes, tiebreak by median score ---
    # Create a sorting key: (-votes, -median) for stable ranking
    ranking_keys = np.column_stack((-vote_counts, -candidate_medians))
    # lexsort sorts by last key first, then by earlier keys
    ranked_indices = np.lexsort((-candidate_medians, -vote_counts))

    top1_idx = ranked_indices[0]
    top1_fish_id = fish_ids[top1_idx]
    top1_frames = per_frame_scores[:, top1_idx]
    top1_score = float(np.median(top1_frames))
    score_dispersion = float(np.std(top1_frames))

    # Winning votes for top1
    winning_votes = int(vote_counts[top1_idx])
    agreement_ratio = winning_votes / Q

    # Top-2
    if num_candidates >= 2:
        top2_idx = ranked_indices[1]
        top2_fish_id = fish_ids[top2_idx]
        top2_score = float(np.median(per_frame_scores[:, top2_idx]))
    else:
        top2_fish_id = None
        top2_score = 0.0

    # Margin: difference between top1 and top2 median scores
    margin = top1_score - top2_score

    logger.debug(
        "Scoring complete: top1=%s (%.4f, %d/%d votes), top2=%s (%.4f), margin=%.4f",
        top1_fish_id,
        top1_score,
        winning_votes,
        Q,
        top2_fish_id,
        top2_score,
        margin,
    )

    return ScoringResult(
        top1_fish_id=top1_fish_id,
        top1_score=top1_score,
        top2_fish_id=top2_fish_id,
        top2_score=top2_score,
        margin=margin,
        agreement_ratio=agreement_ratio,
        winning_votes=winning_votes,
        total_votes=Q,
        candidates_evaluated=num_candidates,
        score_dispersion=score_dispersion,
        per_frame_winners=per_frame_winners,
    )
