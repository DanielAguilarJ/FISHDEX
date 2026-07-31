"""
Linkage document construction.

The linkage document is the audit trail for an identification decision: it records
what the pipeline compared, what it chose, and why. Both outcomes write one — the
repeat-capture path and the definitive (auto_match / new_fish) path — and they
previously built their dicts independently while sharing 18 of ~23 keys. Adding
evidence to one silently omitted it from the other.

These tests pin the shared base and the fields each path legitimately adds.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.job_service import (
    DecisionOutcome,
    LinkageContext,
    build_linkage_base,
    top2_score_or_zero,
)

CONTEXT = LinkageContext(
    area_code="401001",
    latitude=50.1,
    longitude=14.4,
    match_margin=0.0731,
    top2_score=0.7412,
    candidates_evaluated=17,
    quality_score=0.8123,
    track_consistent=True,
    multiple_fish_detected=False,
)

# Keys the repeat-capture path adds on top of the shared base.
REPEAT_ONLY = {
    "is_linked",
    "matched_fish_id",
    "proposed_fish_id",
    "proposed_score",
    "top2_fish_id",
}

# Keys the definitive path adds on top of the shared base.
DEFINITIVE_ONLY = {
    "is_linked",
    "matched_fish_id",
    "final_fish_id",
    "previous_sighting_id",
    "match_confidence",
    "total_sightings_before",
    "total_sightings_after",
    "same_species_required",
    "model_version",
}

SHARED_KEYS = {
    "strategy",
    "threshold",
    "top2_score",
    "margin",
    "confidence_band",
    "decision",
    "requires_human_review",
    "reasons",
    "area_code",
    "latitude",
    "longitude",
    "nearby_area_radius_km",
    "candidates_evaluated",
    "quality_score",
    "track_consistent",
    "multiple_fish_detected",
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared base
# ─────────────────────────────────────────────────────────────────────────────
def test_base_carries_exactly_the_shared_keys() -> None:
    base = build_linkage_base(
        CONTEXT, DecisionOutcome("high", "auto_match", False), reasons=[]
    )

    assert set(base) == SHARED_KEYS


def test_base_records_the_configured_threshold() -> None:
    """
    The threshold in force at decision time is recorded, so a later change to the
    configuration cannot retroactively make a stored decision look wrong.
    """
    base = build_linkage_base(
        CONTEXT, DecisionOutcome("high", "auto_match", False), reasons=[]
    )

    assert base["threshold"] == settings.reid_similarity_threshold


def test_base_propagates_the_decision_outcome() -> None:
    outcome = DecisionOutcome("forced", "auto_match", False)

    base = build_linkage_base(CONTEXT, outcome, reasons=[])

    assert base["confidence_band"] == "forced"
    assert base["decision"] == "auto_match"


def test_scores_are_rounded_to_four_decimals() -> None:
    """Matches what is written to the database, so documents and rows agree."""
    base = build_linkage_base(
        CONTEXT, DecisionOutcome("high", "auto_match", False), reasons=[]
    )

    assert base["margin"] == 0.0731
    assert base["top2_score"] == 0.7412


def test_geographic_evidence_is_preserved() -> None:
    base = build_linkage_base(
        CONTEXT, DecisionOutcome("high", "auto_match", False), reasons=[]
    )

    assert base["area_code"] == "401001"
    assert base["latitude"] == 50.1
    assert base["longitude"] == 14.4
    assert base["nearby_area_radius_km"] == settings.nearby_area_radius_km


def test_quality_and_tracking_evidence_is_preserved() -> None:
    """These three drive the repeat-capture decision, so they must be auditable."""
    base = build_linkage_base(
        CONTEXT, DecisionOutcome("high", "auto_match", False), reasons=[]
    )

    assert base["quality_score"] == 0.8123
    assert base["track_consistent"] is True
    assert base["multiple_fish_detected"] is False


def test_reasons_are_stored_verbatim() -> None:
    reasons = ["margin_below_threshold", "single_candidate"]

    base = build_linkage_base(CONTEXT, DecisionOutcome("x", "y", False), reasons=reasons)

    assert base["reasons"] == reasons


@pytest.mark.parametrize(
    "outcome",
    [
        DecisionOutcome("high", "auto_match", False),
        DecisionOutcome("new_fish", "new_fish", False),
        DecisionOutcome("repeat_capture", "repeat_capture", True),
    ],
)
def test_requires_human_review_is_always_false(outcome: DecisionOutcome) -> None:
    """
    Not a contradiction with the repeat-capture outcome: the manual-review queue
    was removed in favour of forced-decision logic, so no document ever asks a
    human to adjudicate. `decision` carries that information instead.
    """
    base = build_linkage_base(CONTEXT, outcome, reasons=[])

    assert base["requires_human_review"] is False


def test_base_returns_a_fresh_dict_each_call() -> None:
    """Both paths mutate the base with .update(), so it must not be shared state."""
    outcome = DecisionOutcome("high", "auto_match", False)

    first = build_linkage_base(CONTEXT, outcome, reasons=[])
    first["injected"] = True
    second = build_linkage_base(CONTEXT, outcome, reasons=[])

    assert "injected" not in second


def test_context_is_immutable() -> None:
    with pytest.raises(Exception):
        CONTEXT.area_code = "999999"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# Absent runner-up
# ─────────────────────────────────────────────────────────────────────────────
def test_absent_top2_score_becomes_zero() -> None:
    """
    An empty or single-entry gallery yields no runner-up. round(None, 4) would
    raise, so the value is coerced first.
    """
    assert top2_score_or_zero(None) == 0.0


def test_present_top2_score_is_returned_as_float() -> None:
    assert top2_score_or_zero(0.5) == 0.5
    assert isinstance(top2_score_or_zero(1), float)


def test_base_survives_a_missing_runner_up() -> None:
    context = LinkageContext(
        area_code="XX",
        latitude=None,
        longitude=None,
        match_margin=0.0,
        top2_score=None,  # type: ignore[arg-type]
        candidates_evaluated=0,
        quality_score=0.0,
        track_consistent=False,
        multiple_fish_detected=False,
    )

    base = build_linkage_base(context, DecisionOutcome("new_fish", "new_fish", False), [])

    assert base["top2_score"] == 0.0
    assert base["margin"] == 0.0


def test_base_survives_absent_coordinates() -> None:
    """A capture with no GPS must still produce a document."""
    context = LinkageContext(
        area_code="XX",
        latitude=None,
        longitude=None,
        match_margin=0.1,
        top2_score=0.2,
        candidates_evaluated=3,
        quality_score=0.5,
        track_consistent=True,
        multiple_fish_detected=False,
    )

    base = build_linkage_base(context, DecisionOutcome("new_fish", "new_fish", False), [])

    assert base["latitude"] is None
    assert base["longitude"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Path parity
# ─────────────────────────────────────────────────────────────────────────────
def test_both_paths_start_from_an_identical_base() -> None:
    """
    The point of the shared builder: whatever a path adds afterwards, the audit
    evidence underneath is the same.
    """
    outcome = DecisionOutcome("high", "auto_match", False)

    repeat = build_linkage_base(CONTEXT, outcome, reasons=["r"])
    definitive = build_linkage_base(CONTEXT, outcome, reasons=["r"])

    assert repeat == definitive


def test_path_specific_keys_do_not_overlap_the_shared_base() -> None:
    """
    A path must not silently redefine a shared field. `is_linked` and
    `matched_fish_id` are the two both paths set, and neither is in the base.
    """
    overlap_repeat = REPEAT_ONLY & SHARED_KEYS
    overlap_definitive = DEFINITIVE_ONLY & SHARED_KEYS

    assert overlap_repeat == set(), overlap_repeat
    assert overlap_definitive == set(), overlap_definitive


def test_source_builds_both_documents_through_the_shared_helper() -> None:
    """
    Guards against a future path reintroducing a literal dict, which is how the
    two documents drifted apart in the first place.
    """
    import inspect

    from app.services import job_service

    source = inspect.getsource(job_service)
    assert "linkage = {" not in source, "a literal linkage dict was reintroduced"
    assert source.count("build_linkage_base(") >= 3  # definition + both call sites
