"""
Unified Identification Pipeline for FishDex.

Single source of truth for fish identification. Both /api/v1/jobs and
/api/v1/identify must route through this pipeline.

Pipeline steps:
1. validate_capture_metadata
2. validate_gps
3. resolve_czech_area
4. resolve_confirmed_species
5. extract_query_embeddings
6. retrieve_geo_species_candidates
7. build_identity_gallery
8. score_candidates
9. decide_identity
10. stage_artifacts (if definitive)
11. commit_result_atomically (if definitive)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.config import settings
from app.utils.geo import is_within_radius, gps_uncertainty_within_radius
from app.utils.area_utils import normalize_area_code
from app.services.identity_scoring_service import score_candidates, ScoringResult
from app.services.identity_decision_service import (
    decide_identity,
    DecisionContext,
    IdentityDecision,
    DEFAULT_THRESHOLDS,
)

logger = logging.getLogger(__name__)


@dataclass
class CaptureMetadata:
    """Input metadata for the identification pipeline."""
    species_slug: str
    area_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gps_accuracy_m: Optional[float] = None
    gps_timestamp: Optional[str] = None
    gps_is_mocked: bool = False
    gps_source: str = "current"
    area_selection_source: str = "user_selected"
    user_id: Optional[str] = None


@dataclass
class PipelineResult:
    """Output of the identification pipeline."""
    decision: str  # auto_match, new_fish, needs_manual_review, repeat_capture
    fish_id: Optional[str] = None
    proposed_fish_id: Optional[str] = None
    scoring: Optional[ScoringResult] = None
    identity_decision: Optional[IdentityDecision] = None
    candidates_evaluated: int = 0
    minimum_distance_m: Optional[float] = None
    cross_area: bool = False
    model_version: Optional[str] = None
    reasons: list[str] = field(default_factory=list)
    error: Optional[str] = None


class IdentificationPipeline:
    """
    Canonical identification pipeline.

    Responsible for:
    - Retrieving geographically eligible candidates from the embeddings DB
    - Building per-individual gallery prototypes
    - Scoring via multi-frame voting
    - Making the identity decision
    - NOT responsible for: detection, cropping, frame extraction, storage
      (those are handled by the caller before invoking this pipeline)
    """

    def __init__(self):
        from app.services.matching_service import get_matching_service
        self._matching = get_matching_service()
        self._radius_m = (settings.nearby_area_radius_km or 5.0) * 1000.0
        self._model_version = settings.reid_cache_name or "fishencoder_512_v1"

    def run(
        self,
        query_embeddings: np.ndarray,
        metadata: CaptureMetadata,
        quality_score: float = 1.0,
        valid_crop_count: int = 5,
        track_consistent: bool = True,
        multiple_fish_detected: bool = False,
    ) -> PipelineResult:
        """
        Execute the full identification pipeline.

        Args:
            query_embeddings: shape (Q, D) L2-normalized embeddings from the capture
            metadata: CaptureMetadata with GPS, species, area info
            quality_score: 0.0-1.0 quality metric from capture_quality_service
            valid_crop_count: number of valid crops extracted
            track_consistent: whether single-fish tracking was verified
            multiple_fish_detected: whether multiple fish were found in video

        Returns:
            PipelineResult with decision, fish_id, scoring details, and reasons
        """
        try:
            return self._run_internal(
                query_embeddings, metadata,
                quality_score, valid_crop_count,
                track_consistent, multiple_fish_detected,
            )
        except Exception as e:
            logger.exception("Pipeline failed: %s", e)
            return PipelineResult(
                decision="repeat_capture",
                error=str(e),
                reasons=[f"Pipeline error: {e}"],
            )

    def _run_internal(
        self,
        query_embeddings: np.ndarray,
        metadata: CaptureMetadata,
        quality_score: float,
        valid_crop_count: int,
        track_consistent: bool,
        multiple_fish_detected: bool,
    ) -> PipelineResult:
        # --- Step 1: Validate inputs ---
        if query_embeddings.ndim != 2:
            raise ValueError(f"Expected 2D embeddings, got shape {query_embeddings.shape}")

        if not metadata.species_slug:
            raise ValueError("species_slug is required")

        # --- Step 2: Retrieve geo-species candidates ---
        candidates = self._retrieve_candidates(metadata)

        if not candidates:
            # No historical candidates — either new_fish or we need to check quality
            return self._decide_no_candidates(
                metadata, quality_score, valid_crop_count,
                track_consistent, multiple_fish_detected,
            )

        # --- Step 3: Build identity gallery ---
        gallery = self._build_gallery(candidates)

        # --- Step 4: Score candidates ---
        scoring = score_candidates(
            query_embeddings=query_embeddings,
            candidate_gallery=gallery,
            max_support_per_identity=getattr(settings, "reid_max_support_per_identity", 8),
        )

        # --- Step 5: Compute distance context ---
        min_distance_m = None
        cross_area = False
        if scoring.top1_fish_id and scoring.top1_fish_id in candidates:
            candidate_info = candidates[scoring.top1_fish_id]
            min_distance_m = candidate_info.get("min_distance_m")
            matched_area = candidate_info.get("area_code", "XX")
            query_area = normalize_area_code(metadata.area_code)
            cross_area = (matched_area != query_area) and (query_area != "XX") and (matched_area != "XX")

        # --- Step 6: Build decision context ---
        gps_status = self._evaluate_gps_uncertainty(metadata, min_distance_m)

        context = DecisionContext(
            top1_score=scoring.top1_score,
            top2_score=scoring.top2_score,
            margin=scoring.margin,
            agreement_ratio=scoring.agreement_ratio,
            winning_votes=scoring.winning_votes,
            total_votes=scoring.total_votes,
            candidates_evaluated=scoring.candidates_evaluated,
            minimum_distance_m=min_distance_m,
            gps_uncertainty_status=gps_status,
            area_consistency_status="plausible",  # Full validation in Phase 5
            cross_area=cross_area,
            quality_score=quality_score,
            valid_crop_count=valid_crop_count,
            track_consistent=track_consistent,
            multiple_fish_detected=multiple_fish_detected,
            calibration_available=False,  # Phase 7
            index_complete=True,  # Assumed until audit says otherwise
            model_version_compatible=True,
        )

        # --- Step 7: Make decision ---
        decision = decide_identity(
            context=context,
            top1_fish_id=scoring.top1_fish_id,
        )

        return PipelineResult(
            decision=decision.decision,
            fish_id=scoring.top1_fish_id if decision.decision == "auto_match" else None,
            proposed_fish_id=scoring.top1_fish_id if decision.decision == "needs_manual_review" else None,
            scoring=scoring,
            identity_decision=decision,
            candidates_evaluated=scoring.candidates_evaluated,
            minimum_distance_m=min_distance_m,
            cross_area=cross_area,
            model_version=self._model_version,
            reasons=decision.reasons,
        )

    def _retrieve_candidates(self, metadata: CaptureMetadata) -> dict:
        """
        Retrieve eligible candidate embeddings from the database.

        Filters:
        - Same species_slug
        - Compatible model_version
        - GPS distance <= radius (mandatory)

        Returns:
            dict[fish_id -> {"embeddings": list[np.ndarray], "min_distance_m": float, "area_code": str}]
        """
        if metadata.latitude is None or metadata.longitude is None:
            logger.warning("No GPS available — cannot retrieve candidates")
            return {}

        with self._matching._connect() as conn:
            rows = conn.execute(
                """
                SELECT fish_id, embedding, area_code, latitude, longitude
                FROM fish_embeddings
                WHERE species_slug = ? AND model_version = ?
                """,
                (metadata.species_slug, self._model_version),
            ).fetchall()

        if not rows:
            return {}

        # Group by fish_id, filter by GPS
        candidates: dict = {}

        for fish_id, emb_blob, stored_area, stored_lat, stored_lng in rows:
            within, distance_m = is_within_radius(
                metadata.latitude, metadata.longitude,
                stored_lat, stored_lng,
                radius_m=self._radius_m,
            )
            if not within:
                continue

            emb = np.frombuffer(emb_blob, dtype=np.float32)

            if fish_id not in candidates:
                candidates[fish_id] = {
                    "embeddings": [],
                    "min_distance_m": distance_m or 0.0,
                    "area_code": normalize_area_code(stored_area),
                }

            candidates[fish_id]["embeddings"].append(emb)

            if distance_m is not None and distance_m < candidates[fish_id]["min_distance_m"]:
                candidates[fish_id]["min_distance_m"] = distance_m

        return candidates

    def _build_gallery(self, candidates: dict) -> dict[str, np.ndarray]:
        """
        Convert raw candidate embeddings into numpy arrays suitable for scoring.

        Returns:
            dict[fish_id -> np.ndarray of shape (S, D)]
        """
        gallery: dict[str, np.ndarray] = {}
        for fish_id, info in candidates.items():
            embs = info["embeddings"]
            if embs:
                gallery[fish_id] = np.stack(embs)
        return gallery

    def _evaluate_gps_uncertainty(
        self, metadata: CaptureMetadata, distance_m: Optional[float]
    ) -> str:
        """
        Evaluate GPS uncertainty status.
        
        If distance is well within the radius (< 80% of limit) and query has
        good accuracy, treat as "guaranteed_inside" even without historical accuracy.
        This prevents every match from going to review just because old embeddings
        lack accuracy metadata.
        """
        if distance_m is None:
            return "unknown"

        # If well within radius with reasonable query accuracy, don't penalize
        # for missing historical accuracy (which is expected until Phase 5 Flutter fix)
        if metadata.gps_accuracy_m is not None:
            # Conservative: if distance + query_accuracy < 80% of radius, call it guaranteed
            margin_threshold = self._radius_m * 0.8
            if distance_m + metadata.gps_accuracy_m < margin_threshold:
                return "guaranteed_inside"

        return gps_uncertainty_within_radius(
            distance_m=distance_m,
            query_accuracy_m=metadata.gps_accuracy_m,
            historical_accuracy_m=None,  # Not available per-embedding yet
            radius_m=self._radius_m,
        )

    def _decide_no_candidates(
        self,
        metadata: CaptureMetadata,
        quality_score: float,
        valid_crop_count: int,
        track_consistent: bool,
        multiple_fish_detected: bool,
    ) -> PipelineResult:
        """Handle the case where no candidates exist in the database."""
        reasons = []

        # Check quality gates first
        if multiple_fish_detected:
            return PipelineResult(
                decision="repeat_capture",
                reasons=["Multiple fish detected"],
                model_version=self._model_version,
            )

        if quality_score < DEFAULT_THRESHOLDS.get("min_quality_score", 0.4):
            return PipelineResult(
                decision="repeat_capture",
                reasons=["Quality too low for reliable identification"],
                model_version=self._model_version,
            )

        if not track_consistent:
            return PipelineResult(
                decision="repeat_capture",
                reasons=["Inconsistent fish tracking"],
                model_version=self._model_version,
            )

        min_frames = DEFAULT_THRESHOLDS.get("min_query_frames", 3)
        if valid_crop_count < min_frames:
            return PipelineResult(
                decision="repeat_capture",
                reasons=[f"Insufficient frames ({valid_crop_count} < {min_frames})"],
                model_version=self._model_version,
            )

        # Quality OK, no candidates -> new fish
        if metadata.latitude is None or metadata.longitude is None:
            reasons.append("No GPS — cannot confirm absence of candidates")
            return PipelineResult(
                decision="needs_manual_review",
                reasons=reasons,
                model_version=self._model_version,
            )

        return PipelineResult(
            decision="new_fish",
            reasons=["No candidates within radius — new individual"],
            model_version=self._model_version,
        )


# Singleton
_pipeline_instance: Optional[IdentificationPipeline] = None


def get_identification_pipeline() -> IdentificationPipeline:
    """Return the singleton IdentificationPipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = IdentificationPipeline()
    return _pipeline_instance
