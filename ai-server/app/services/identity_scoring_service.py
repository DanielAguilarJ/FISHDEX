"""
Identity Scoring Service for FishDex.

Implements per-individual scoring with multi-frame voting:
1. Each query frame votes for its most similar candidate
2. Winner is determined by vote count, then by median score
3. Returns top-1, top-2, margin, agreement, and per-frame breakdown
4. Selects the best historical reference sighting for the winner
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceEvidence:
    """The exact historical embedding/sighting used as best visual evidence."""

    embedding_id: Optional[str] = None
    sighting_id: Optional[str] = None
    score: float = 0.0
    area_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_m: Optional[float] = None
    created_at: Optional[str] = None


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

    # Reference evidence: the best historical sighting for the winning identity
    reference: Optional[ReferenceEvidence] = None


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
        reference=None,
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


@dataclass
class SupportMetadata:
    """Metadata for a single support embedding row."""

    embedding_id: Optional[str] = None
    sighting_id: Optional[str] = None
    area_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_m: Optional[float] = None
    created_at: Optional[str] = None


def _select_best_reference(
    query_embeddings: np.ndarray,
    winner_support: np.ndarray,
    winner_metadata: list[SupportMetadata],
) -> Optional[ReferenceEvidence]:
    """
    Select the best historical reference for the winning identity.

    Algorithm:
    1. Compute similarity matrix: query_frames x winner_supports
    2. For each support embedding, compute the median similarity across all query frames
    3. The support with the highest median is the best visual reference
    4. If multiple supports belong to the same sighting_id, group by sighting
       and select the best sighting (highest median of its supports' medians)
    """
    if winner_support.shape[0] == 0 or not winner_metadata:
        return None

    # Ensure normalized
    query_norm = _l2_normalize(query_embeddings)
    support_norm = _l2_normalize(winner_support)

    # (Q, S) similarity matrix
    similarity_matrix = query_norm @ support_norm.T

    # Median similarity per support across all query frames
    support_scores = np.median(similarity_matrix, axis=0)  # (S,)

    # Group by sighting_id to find best sighting
    sighting_groups: dict[str, list[tuple[int, float]]] = {}
    for idx, meta in enumerate(winner_metadata):
        key = meta.sighting_id or f"_no_sighting_{idx}"
        if key not in sighting_groups:
            sighting_groups[key] = []
        sighting_groups[key].append((idx, float(support_scores[idx])))

    # Find the best sighting: highest median score among its supports
    best_sighting_score: float = -1.0
    best_support_idx: int = 0

    for sighting_key, entries in sighting_groups.items():
        scores = [s for _, s in entries]
        sighting_median = float(np.median(scores))
        if sighting_median > best_sighting_score:
            best_sighting_score = sighting_median
            # NOTE: the winning sighting id is not tracked separately — it is
            # already reachable as best_meta.sighting_id below, and the two are
            # equivalent (a synthesised "_no_sighting_*" key only arises when
            # meta.sighting_id is None).
            # Pick the support with the highest individual score within this sighting
            best_entry = max(entries, key=lambda e: e[1])
            best_support_idx = best_entry[0]

    best_meta = winner_metadata[best_support_idx]
    best_score = float(support_scores[best_support_idx])

    return ReferenceEvidence(
        embedding_id=best_meta.embedding_id,
        sighting_id=best_meta.sighting_id,
        score=best_score,
        area_code=best_meta.area_code,
        latitude=best_meta.latitude,
        longitude=best_meta.longitude,
        distance_m=best_meta.distance_m,
        created_at=best_meta.created_at,
    )


def score_candidates(
    query_embeddings: np.ndarray,
    candidate_gallery: dict[str, np.ndarray],
    candidate_support_metadata: Optional[dict[str, list[SupportMetadata]]] = None,
    max_support_per_identity: int = 8,
) -> ScoringResult:
    """
    Score query embeddings against a candidate gallery.

    Args:
        query_embeddings: shape (Q, D) — L2-normalized query frame embeddings
        candidate_gallery: dict mapping fish_id -> shape (S, D) support embeddings
        candidate_support_metadata: dict mapping fish_id -> list of SupportMetadata
            aligned positionally with the support embeddings
        max_support_per_identity: max supports to use per individual (balancing)

    Returns:
        ScoringResult with full scoring breakdown and reference evidence

    Algorithm:
    1. For each candidate, limit support set and L2-normalize.
    2. For each query frame, compute robust score vs each candidate:
       similarities = q @ S_i.T, robust_score = median of top-k values.
    3. Each frame votes for its best candidate.
    4. Aggregate: winner by votes, then median score as tiebreak.
    5. Compute margin, agreement, dispersion.
    6. Select best reference from winner's supports.
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

    # Track which supports survive sampling for the winner (for reference selection)
    sampled_supports: dict[str, tuple[np.ndarray, list[SupportMetadata]]] = {}

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

        # Get metadata if available
        meta_list = (
            candidate_support_metadata.get(fish_id)
            if candidate_support_metadata
            else None
        )

        # Limit support set size (random sample without replacement)
        S_i = support.shape[0]
        if S_i > max_support_per_identity:
            # Use hashlib for deterministic seed across processes
            stable_seed = int.from_bytes(
                hashlib.sha256(fish_id.encode()).digest()[:8], "big"
            )
            rng = np.random.default_rng(seed=stable_seed & 0xFFFFFFFF)
            indices = rng.choice(S_i, size=max_support_per_identity, replace=False)
            support = support[indices]
            # Apply same sampling to metadata
            if meta_list and len(meta_list) == S_i:
                meta_list = [meta_list[i] for i in indices]
            S_i = max_support_per_identity

        # L2-normalize support
        support = _l2_normalize(support)

        # Store sampled supports for reference selection later
        sampled_supports[fish_id] = (support, meta_list or [])

        # Compute similarities: (Q, S_i) via matrix multiplication
        similarities = query_embeddings @ support.T  # (Q, S_i)

        # Robust score per frame: median of top-k similarities
        k = min(3, S_i)

        if k == S_i:
            per_frame_scores[:, c_idx] = np.median(
                np.sort(similarities, axis=1)[:, -k:], axis=1
            )
        else:
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

    # Margin: difference between top1 and top2 median scores.
    # IMPORTANT: When there is only one candidate, margin is NOT meaningful.
    # We set it to 0.0 to signal "not available" rather than the misleading
    # top1_score - 0.0 which creates an artificially huge margin.
    # The decision service must rely on single_candidate_threshold instead.
    if num_candidates >= 2:
        margin = top1_score - top2_score
    else:
        margin = 0.0

    # --- Step 6: Select best reference from winner's supports ---
    reference: Optional[ReferenceEvidence] = None
    winner_data = sampled_supports.get(top1_fish_id)
    if winner_data and winner_data[1]:  # has metadata
        winner_support_arr, winner_meta = winner_data
        reference = _select_best_reference(
            query_embeddings, winner_support_arr, winner_meta
        )

    logger.debug(
        "Scoring complete: top1=%s (%.4f, %d/%d votes), top2=%s (%.4f), margin=%.4f, ref=%s",
        top1_fish_id,
        top1_score,
        winning_votes,
        Q,
        top2_fish_id,
        top2_score,
        margin,
        reference.sighting_id if reference else None,
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
        reference=reference,
    )
