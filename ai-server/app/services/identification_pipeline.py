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
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.config import settings
from app.utils.geo import is_within_radius, gps_uncertainty_within_radius
from app.utils.area_utils import normalize_area_code
from app.services.identity_scoring_service import (
    score_candidates,
    ScoringResult,
    SupportMetadata,
    ReferenceEvidence,
)
from app.services.identity_decision_service import (
    decide_identity,
    DecisionContext,
    IdentityDecision,
    DEFAULT_THRESHOLDS,
)
from app.calibration import load_calibration, get_thresholds_for_species

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
    decision: str  # auto_match, new_fish, repeat_capture (never needs_manual_review)
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

    # Reference evidence fields (propagated from ScoringResult.reference)
    reference_embedding_id: Optional[str] = None
    reference_sighting_id: Optional[str] = None
    reference_score: float = 0.0
    reference_area_code: Optional[str] = None
    reference_latitude: Optional[float] = None
    reference_longitude: Optional[float] = None
    reference_distance_m: Optional[float] = None
    reference_created_at: Optional[str] = None


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
        """Resolve the matching, scoring and decision services this pipeline uses."""
        from app.services.matching_service import get_matching_service
        self._matching = get_matching_service()
        self._auto_match_radius_m = (
            getattr(settings, "reid_auto_match_radius_km", None)
            or settings.nearby_area_radius_km
            or 5.0
        ) * 1000.0
        self._review_search_radius_m = (
            getattr(settings, "reid_review_search_radius_km", None) or 50.0
        ) * 1000.0
        self._model_version = settings.reid_cache_name or "fishencoder_512_v1"
        # Check if calibration exists for this model version
        self._calibration = load_calibration(self._model_version)
        self._calibration_available = self._calibration is not None

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
        """
        Execute the identification stages for one capture.

        Args:
            query_embeddings: L2-normalised query matrix of shape (N, D).
            metadata: Validated capture metadata.

        Returns:
            The pipeline result carrying the decision and its supporting evidence.
        """
        if query_embeddings.ndim != 2:
            raise ValueError(f"Expected 2D embeddings, got shape {query_embeddings.shape}")

        if not metadata.species_slug:
            raise ValueError("species_slug is required")

        # --- Step 2: Retrieve geo-species candidates (two-level search) ---
        candidates = self._retrieve_candidates(metadata)

        if not candidates:
            # No historical candidates — either new_fish or we need to check quality
            return self._decide_no_candidates(
                metadata, quality_score, valid_crop_count,
                track_consistent, multiple_fish_detected,
            )

        # --- Step 3: Build identity gallery with metadata ---
        gallery, gallery_metadata = self._build_gallery(candidates)

        # --- Step 4: Score candidates ---
        scoring = score_candidates(
            query_embeddings=query_embeddings,
            candidate_gallery=gallery,
            candidate_support_metadata=gallery_metadata,
            max_support_per_identity=settings.reid_max_support_images_per_identity,
        )

        # --- Step 5: Compute distance context ---
        min_distance_m = None
        cross_area = False
        outside_auto_match_radius = False

        if scoring.top1_fish_id and scoring.top1_fish_id in candidates:
            candidate_info = candidates[scoring.top1_fish_id]
            min_distance_m = candidate_info.get("min_distance_m")

            # Use reference's area for cross_area if available
            if scoring.reference and scoring.reference.area_code:
                matched_area = normalize_area_code(scoring.reference.area_code)
            else:
                matched_area = candidate_info.get("area_code", "XX")

            query_area = normalize_area_code(metadata.area_code)
            cross_area = (
                (matched_area != query_area)
                and (query_area != "XX")
                and (matched_area != "XX")
            )

            # Check if outside auto-match radius but inside review radius
            if min_distance_m is not None and min_distance_m > self._auto_match_radius_m:
                outside_auto_match_radius = True

        # --- Step 6: Build decision context ---
        gps_status = self._evaluate_gps_uncertainty(metadata, min_distance_m)

        # Get calibrated thresholds for this species
        calibrated_thresholds, calibration_available = get_thresholds_for_species(
            species_slug=metadata.species_slug,
            model_version=self._model_version,
        )

        decision_thresholds = {
            "review_threshold": calibrated_thresholds.review_threshold,
            "auto_match_threshold": calibrated_thresholds.auto_match_threshold,
            "single_candidate_threshold": calibrated_thresholds.single_candidate_threshold,
            "min_margin": calibrated_thresholds.min_margin,
            "min_agreement": calibrated_thresholds.min_agreement,
        }

        index_complete = self._check_index_completeness()

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
            calibration_available=calibration_available,
            index_complete=index_complete,
            model_version_compatible=True,
        )

        # --- Step 7: Make decision ---
        decision = decide_identity(
            context=context,
            top1_fish_id=scoring.top1_fish_id,
            thresholds=decision_thresholds,
        )

        # Note if outside auto-match radius (keep auto_match, just log it)
        final_decision = decision.decision
        final_reasons = list(decision.reasons)

        if (
            outside_auto_match_radius
            and final_decision == "auto_match"
        ):
            final_reasons.append(
                f"Note: outside_auto_match_radius "
                f"(distance={min_distance_m:.0f}m > {self._auto_match_radius_m:.0f}m) "
                f"— match kept as auto_match per no-manual-review policy"
            )

        # --- Build result with reference evidence ---
        ref = scoring.reference

        return PipelineResult(
            decision=final_decision,
            fish_id=scoring.top1_fish_id if final_decision == "auto_match" else None,
            proposed_fish_id=decision.proposed_fish_id if final_decision == "auto_match" and decision.confidence_band == "forced" else None,
            scoring=scoring,
            identity_decision=decision,
            candidates_evaluated=scoring.candidates_evaluated,
            minimum_distance_m=min_distance_m,
            cross_area=cross_area,
            model_version=self._model_version,
            reasons=final_reasons,
            # Reference evidence
            reference_embedding_id=ref.embedding_id if ref else None,
            reference_sighting_id=ref.sighting_id if ref else None,
            reference_score=ref.score if ref else 0.0,
            reference_area_code=ref.area_code if ref else None,
            reference_latitude=ref.latitude if ref else None,
            reference_longitude=ref.longitude if ref else None,
            reference_distance_m=ref.distance_m if ref else None,
            reference_created_at=ref.created_at if ref else None,
        )

    def _retrieve_candidates(self, metadata: CaptureMetadata) -> dict:
        """
        Retrieve eligible candidate embeddings from the database.

        Two-level geographic search:
        - Within auto_match_radius: candidates eligible for auto_match
        - Within review_search_radius: candidates eligible for manual review
          (marked with "review_only" flag)

        Returns:
            dict[fish_id -> {
                "embeddings": list[np.ndarray],
                "supports": list[SupportMetadata],
                "min_distance_m": float,
                "area_code": str,
                "review_only": bool,
            }]
        """
        if metadata.latitude is None or metadata.longitude is None:
            logger.warning("No GPS available — cannot retrieve candidates")
            return {}

        with self._matching._connect() as conn:
            # Try filtered query first (post-migration 006: verification_status exists)
            try:
                rows = conn.execute(
                    """
                    SELECT id, fish_id, sighting_id, embedding, area_code,
                           latitude, longitude, created_at, model_version
                    FROM fish_embeddings
                    WHERE species_slug = ? AND model_version = ?
                      AND verification_status IN ('anchor_new', 'human_confirmed')
                    """,
                    (metadata.species_slug, self._model_version),
                ).fetchall()
            except sqlite3.OperationalError as exc:
                # Only a missing column should reach the fallback; a connection or
                # disk error must not be mistaken for a pre-migration schema.
                logger.warning(
                    "verification_status query failed (%s); using pre-migration "
                    "fallback query",
                    exc,
                )
                rows = conn.execute(
                    """
                    SELECT id, fish_id, sighting_id, embedding, area_code,
                           latitude, longitude, created_at, model_version
                    FROM fish_embeddings
                    WHERE species_slug = ? AND model_version = ?
                    """,
                    (metadata.species_slug, self._model_version),
                ).fetchall()

        if not rows:
            return {}

        # Group by fish_id, filter by GPS (two-level)
        candidates: dict = {}

        for row in rows:
            emb_id = row[0]
            fish_id = row[1]
            sighting_id = row[2]
            emb_blob = row[3]
            stored_area = row[4]
            stored_lat = row[5]
            stored_lng = row[6]
            created_at = row[7]
            # row[8] = model_version (already filtered in query)

            within_review, distance_m = is_within_radius(
                metadata.latitude, metadata.longitude,
                stored_lat, stored_lng,
                radius_m=self._review_search_radius_m,
            )
            if not within_review:
                continue

            # Determine if within auto-match radius
            within_auto = (
                distance_m is not None and distance_m <= self._auto_match_radius_m
            )

            emb = np.frombuffer(emb_blob, dtype=np.float32)
            support_meta = SupportMetadata(
                embedding_id=emb_id if isinstance(emb_id, str) else str(emb_id),
                sighting_id=sighting_id,
                area_code=normalize_area_code(stored_area),
                latitude=stored_lat,
                longitude=stored_lng,
                distance_m=distance_m,
                created_at=created_at,
            )

            if fish_id not in candidates:
                candidates[fish_id] = {
                    "embeddings": [],
                    "supports": [],
                    "min_distance_m": distance_m or 0.0,
                    "area_code": normalize_area_code(stored_area),
                    "review_only": not within_auto,
                }

            candidates[fish_id]["embeddings"].append(emb)
            candidates[fish_id]["supports"].append(support_meta)

            if distance_m is not None and distance_m < candidates[fish_id]["min_distance_m"]:
                candidates[fish_id]["min_distance_m"] = distance_m

            # If any embedding is within auto radius, the fish is auto-eligible
            if within_auto:
                candidates[fish_id]["review_only"] = False

        return candidates

    def _build_gallery(
        self, candidates: dict
    ) -> tuple[dict[str, np.ndarray], dict[str, list[SupportMetadata]]]:
        """
        Convert raw candidate embeddings into numpy arrays suitable for scoring.

        Returns:
            tuple of:
            - dict[fish_id -> np.ndarray of shape (S, D)]
            - dict[fish_id -> list[SupportMetadata]] (aligned with embeddings)
        """
        gallery: dict[str, np.ndarray] = {}
        gallery_metadata: dict[str, list[SupportMetadata]] = {}
        for fish_id, info in candidates.items():
            embs = info["embeddings"]
            supports = info["supports"]
            if embs:
                gallery[fish_id] = np.stack(embs)
                gallery_metadata[fish_id] = supports
        return gallery, gallery_metadata

    def _evaluate_gps_uncertainty(
        self, metadata: CaptureMetadata, distance_m: Optional[float]
    ) -> str:
        """
        Evaluate GPS uncertainty status.
        
        If distance is well within the radius (< 80% of limit) and query has
        good accuracy, treat as "guaranteed_inside" even without historical accuracy.
        """
        if distance_m is None:
            return "unknown"

        if metadata.gps_accuracy_m is not None:
            margin_threshold = self._auto_match_radius_m * 0.8
            if distance_m + metadata.gps_accuracy_m < margin_threshold:
                return "guaranteed_inside"

        return gps_uncertainty_within_radius(
            distance_m=distance_m,
            query_accuracy_m=metadata.gps_accuracy_m,
            historical_accuracy_m=None,
            radius_m=self._auto_match_radius_m,
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

        min_frames = DEFAULT_THRESHOLDS.get("min_query_frames", 1)
        if valid_crop_count < min_frames:
            return PipelineResult(
                decision="repeat_capture",
                reasons=[f"Insufficient frames ({valid_crop_count} < {min_frames})"],
                model_version=self._model_version,
            )

        # Quality OK, no candidates -> new fish
        if metadata.latitude is None or metadata.longitude is None:
            reasons.append("No GPS — treating as new fish (no candidates retrievable)")
            return PipelineResult(
                decision="new_fish",
                reasons=reasons,
                model_version=self._model_version,
            )

        return PipelineResult(
            decision="new_fish",
            reasons=["No candidates within radius — new individual"],
            model_version=self._model_version,
        )

    def _check_index_completeness(self) -> bool:
        """Check if the active model_version has sufficient embedding coverage.

        Returns False if the active model_version has zero embeddings in the DB,
        which blocks auto_match in decide_identity() to prevent duplicate
        identities when the index hasn't been rebuilt yet.
        """
        try:
            counts = self._matching.count_active_embeddings(self._model_version)
            active_embeddings = counts.get("embedding_count", 0)

            if active_embeddings == 0:
                logger.warning(
                    "Index completeness check: 0 embeddings for model_version=%s "
                    "— index_complete=False (auto_match blocked)",
                    self._model_version,
                )
                return False

            return True
        except Exception as exc:
            # Fail-open on error: don't block startup on transient DB issues
            logger.warning(
                "Index completeness check failed (assuming complete): %s",
                exc,
            )
            return True


# Singleton
_pipeline_instance: Optional[IdentificationPipeline] = None
_pipeline_instance_lock = threading.Lock()


def get_identification_pipeline() -> IdentificationPipeline:
    """
    Return the process-wide IdentificationPipeline singleton.

    Uses double-checked locking so concurrent first-callers cannot each build a
    pipeline (and therefore each resolve its own model/service handles).

    Returns:
        The shared IdentificationPipeline instance.
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_instance_lock:
            if _pipeline_instance is None:
                _pipeline_instance = IdentificationPipeline()
    return _pipeline_instance
