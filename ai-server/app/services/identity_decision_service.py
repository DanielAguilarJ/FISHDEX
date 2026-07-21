"""
Identity Decision Service for FishDex.

Separates the decision logic from scoring:
- auto_match: high confidence, margin, agreement
- new_fish: no candidate above threshold with good quality
- needs_manual_review: ambiguous zone
- repeat_capture: quality too low to decide
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecisionContext:
    """Context needed to make an identity decision."""

    # From scoring
    top1_score: float
    top2_score: float
    margin: float
    agreement_ratio: float
    winning_votes: int
    total_votes: int
    candidates_evaluated: int

    # From GPS/area
    minimum_distance_m: Optional[float]
    gps_uncertainty_status: str  # "guaranteed_inside", "inside_but_uncertain", "outside", "unknown"
    area_consistency_status: str  # "plausible", "mismatch", "unverifiable", "user_confirmed"
    cross_area: bool

    # From quality
    quality_score: float  # 0.0-1.0
    valid_crop_count: int
    track_consistent: bool
    multiple_fish_detected: bool

    # From model/index
    calibration_available: bool
    index_complete: bool
    model_version_compatible: bool


@dataclass(frozen=True)
class IdentityDecision:
    """The final identity decision."""

    decision: str  # "auto_match", "new_fish", "needs_manual_review", "repeat_capture"
    confidence_band: str  # "high", "medium", "gray_zone", "low", "new_fish"
    reasons: list[str]  # Human-readable reasons

    # For review cases
    proposed_fish_id: Optional[str] = None
    review_required: bool = False


# Configurable thresholds (will come from calibration file in Phase 7)
DEFAULT_THRESHOLDS = {
    "auto_match_threshold": 0.85,
    "review_threshold": 0.70,
    "single_candidate_threshold": 0.88,
    "min_margin": 0.05,
    "min_agreement": 0.70,
    "min_query_frames": 3,
    "min_quality_score": 0.4,
}


def decide_identity(
    context: DecisionContext,
    top1_fish_id: Optional[str],
    thresholds: Optional[dict] = None,
) -> IdentityDecision:
    """
    Make an identity decision based on scoring context and quality.

    Evaluation order:
      1. repeat_capture - data quality too low to trust any result
      2. new_fish - no viable candidate exists
      3. auto_match - all conditions met for confident match
      4. needs_manual_review - ambiguous, human must decide

    Returns an IdentityDecision with all applicable reasons collected.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    reasons: list[str] = []

    # ──────────────────────────────────────────────────────────────────────
    # 1. repeat_capture — quality gate
    # ──────────────────────────────────────────────────────────────────────
    repeat_reasons = _check_repeat_capture(context, t)
    if repeat_reasons:
        logger.info(
            "Decision: repeat_capture — %s", "; ".join(repeat_reasons)
        )
        return IdentityDecision(
            decision="repeat_capture",
            confidence_band="low",
            reasons=repeat_reasons,
        )

    # ──────────────────────────────────────────────────────────────────────
    # 2. new_fish — no candidate survives
    # ──────────────────────────────────────────────────────────────────────
    new_fish_reasons = _check_new_fish(context, top1_fish_id, t)
    if new_fish_reasons:
        logger.info("Decision: new_fish — %s", "; ".join(new_fish_reasons))
        return IdentityDecision(
            decision="new_fish",
            confidence_band="new_fish",
            reasons=new_fish_reasons,
        )

    # ──────────────────────────────────────────────────────────────────────
    # 3. auto_match — all conditions must pass simultaneously
    # ──────────────────────────────────────────────────────────────────────
    auto_match_failures = _check_auto_match(context, t)
    if not auto_match_failures:
        reasons_match = ["All auto-match criteria satisfied"]
        if not context.calibration_available:
            reasons_match.append(
                "Warning: using global defaults (calibration unavailable)"
            )
        logger.info(
            "Decision: auto_match for fish_id=%s — %s",
            top1_fish_id,
            "; ".join(reasons_match),
        )
        return IdentityDecision(
            decision="auto_match",
            confidence_band="high",
            reasons=reasons_match,
            proposed_fish_id=top1_fish_id,
        )

    # ──────────────────────────────────────────────────────────────────────
    # 4. needs_manual_review — everything else
    # ──────────────────────────────────────────────────────────────────────
    review_reasons = _build_review_reasons(context, auto_match_failures, t)
    band = _classify_confidence_band(context, t)

    logger.info(
        "Decision: needs_manual_review for fish_id=%s — %s",
        top1_fish_id,
        "; ".join(review_reasons),
    )
    return IdentityDecision(
        decision="needs_manual_review",
        confidence_band=band,
        reasons=review_reasons,
        proposed_fish_id=top1_fish_id,
        review_required=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Internal checkers
# ──────────────────────────────────────────────────────────────────────────────


def _check_repeat_capture(
    ctx: DecisionContext, t: dict
) -> list[str]:
    """Return reasons if this capture should be rejected as repeat/unusable."""
    reasons: list[str] = []

    if ctx.multiple_fish_detected:
        reasons.append("Multiple fish detected in frame")

    if ctx.quality_score < t["min_quality_score"]:
        reasons.append(
            f"Quality too low ({ctx.quality_score:.2f} < {t['min_quality_score']:.2f})"
        )

    if ctx.valid_crop_count < t["min_query_frames"]:
        reasons.append(
            f"Insufficient frames ({ctx.valid_crop_count} < {t['min_query_frames']})"
        )

    if not ctx.track_consistent:
        reasons.append("Inconsistent track across frames")

    return reasons


def _check_new_fish(
    ctx: DecisionContext,
    top1_fish_id: Optional[str],
    t: dict,
) -> list[str]:
    """Return reasons if this should be classified as a new fish."""
    reasons: list[str] = []

    if ctx.candidates_evaluated == 0 and ctx.index_complete:
        reasons.append("No candidates in range (empty index search)")
        return reasons

    if top1_fish_id is None:
        reasons.append("No match found (no candidate ID)")
        return reasons

    if ctx.top1_score < t["review_threshold"]:
        reasons.append(
            f"Top score below review threshold "
            f"({ctx.top1_score:.3f} < {t['review_threshold']:.2f})"
        )

    return reasons


def _check_auto_match(ctx: DecisionContext, t: dict) -> list[str]:
    """
    Return a list of auto-match conditions that FAILED.
    Empty list means all conditions passed.
    """
    failures: list[str] = []

    # Score threshold
    if ctx.top1_score < t["auto_match_threshold"]:
        failures.append(
            f"Score below auto-match threshold "
            f"({ctx.top1_score:.3f} < {t['auto_match_threshold']:.2f})"
        )

    # Margin check (relaxed for single-candidate with high score)
    single_candidate_pass = (
        ctx.candidates_evaluated == 1
        and ctx.top1_score >= t["single_candidate_threshold"]
    )
    if ctx.margin < t["min_margin"] and not single_candidate_pass:
        failures.append(
            f"Margin too small ({ctx.margin:.3f} < {t['min_margin']:.2f})"
        )

    # Agreement
    if ctx.agreement_ratio < t["min_agreement"]:
        failures.append(
            f"Agreement too low "
            f"({ctx.agreement_ratio:.2f} < {t['min_agreement']:.2f})"
        )

    # GPS/area
    if ctx.gps_uncertainty_status not in (
        "guaranteed_inside",
        "inside_but_uncertain",
        "unknown",
    ):
        failures.append(
            f"GPS status not confirmed ({ctx.gps_uncertainty_status})"
        )

    if ctx.area_consistency_status == "mismatch":
        failures.append("Area consistency mismatch")

    # Quality (already passed repeat_capture gate, but auto-match is stricter)
    if ctx.quality_score < t["min_quality_score"]:
        failures.append(
            f"Quality below minimum ({ctx.quality_score:.2f})"
        )

    # Model/index integrity
    if not ctx.model_version_compatible:
        failures.append("Model version incompatible with stored embeddings")

    if not ctx.index_complete:
        failures.append("Index incomplete (partial search)")

    # Calibration: BLOCK auto_match if calibration is unavailable.
    # While MODEL_VALIDATED=false, all matches must go to manual review.
    if not ctx.calibration_available:
        failures.append(
            "Calibration unavailable (MODEL_VALIDATED=false) — "
            "auto_match disabled until scientific validation"
        )

    return failures


def _build_review_reasons(
    ctx: DecisionContext,
    auto_match_failures: list[str],
    t: dict,
) -> list[str]:
    """Assemble all reasons why manual review is needed."""
    reasons: list[str] = list(auto_match_failures)

    # Add contextual information
    if ctx.cross_area:
        reasons.append("Cross-area match (fish moved between areas)")

    if not ctx.calibration_available:
        reasons.append("Calibration data unavailable for this species/area")

    if (
        ctx.candidates_evaluated == 1
        and ctx.top1_score < t["single_candidate_threshold"]
    ):
        reasons.append(
            f"Single candidate not conclusive "
            f"({ctx.top1_score:.3f} < {t['single_candidate_threshold']:.2f})"
        )

    return reasons


def _classify_confidence_band(ctx: DecisionContext, t: dict) -> str:
    """Classify the confidence band for review UI prioritization."""
    if ctx.top1_score >= t["auto_match_threshold"]:
        # High score but failed on margin/agreement/GPS
        return "medium"
    elif ctx.top1_score >= t["review_threshold"]:
        return "gray_zone"
    else:
        return "low"
