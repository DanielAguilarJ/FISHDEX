"""
Pipeline decision mapping and idempotency payload consistency.

Two behaviours inside the critical transaction are pinned here:

1. How a pipeline decision becomes persistence behaviour. This gate decides
   whether a capture is written into the identity gallery at all, so a wrong
   mapping either loses the angler's data or contaminates the gallery.
2. That both idempotency checks — Phase 1 before any work, Phase 2 inside the
   write lock — return the same response shape. Phase 2 used to build its own
   dict and omit ``classification_confidence``.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.services.job_service import (
    DecisionOutcome,
    _build_skip_result,
    _map_pipeline_decision,
)


class _IdentityDecision:
    """Stand-in for the pipeline's identity decision object."""

    def __init__(self, confidence_band: str | None) -> None:
        """Store the band the pipeline reported."""
        self.confidence_band = confidence_band


# ─────────────────────────────────────────────────────────────────────────────
# Decision mapping
# ─────────────────────────────────────────────────────────────────────────────
def test_auto_match_does_not_require_review() -> None:
    outcome = _map_pipeline_decision("job-1", "auto_match", _IdentityDecision("high"))

    assert outcome == DecisionOutcome("high", "auto_match", False)


def test_auto_match_preserves_a_forced_confidence_band() -> None:
    """
    'forced' records that the decision came from the forced-decision path rather
    than clearing the threshold outright. Losing that label would erase the
    provenance of a lower-confidence link.
    """
    outcome = _map_pipeline_decision("job-1", "auto_match", _IdentityDecision("forced"))

    assert outcome.confidence_band == "forced"


def test_auto_match_defaults_the_band_when_absent() -> None:
    assert _map_pipeline_decision("job-1", "auto_match", None).confidence_band == "high"


def test_auto_match_defaults_the_band_when_none() -> None:
    """An identity decision carrying an explicit None must not leak it downstream."""
    outcome = _map_pipeline_decision("job-1", "auto_match", _IdentityDecision(None))

    assert outcome.confidence_band == "high"


def test_new_fish_does_not_require_review() -> None:
    assert _map_pipeline_decision("job-1", "new_fish") == DecisionOutcome(
        "new_fish", "new_fish", False
    )


def test_repeat_capture_requires_review() -> None:
    """
    repeat_capture is the only outcome that requires review, and it is what stops
    a low-quality capture from being written into the gallery.
    """
    outcome = _map_pipeline_decision("job-1", "repeat_capture")

    assert outcome == DecisionOutcome("repeat_capture", "repeat_capture", True)
    assert outcome.requires_human_review is True


@pytest.mark.parametrize(
    "unexpected",
    ["needs_manual_review", "", "AUTO_MATCH", "unknown", "None"],
)
def test_unexpected_decision_falls_back_to_new_fish(unexpected: str) -> None:
    """
    Fails open, deliberately: refusing to store the capture would lose the
    angler's data, whereas creating a new identity is recoverable by a later
    merge. Note this is case-sensitive — 'AUTO_MATCH' is not 'auto_match'.
    """
    outcome = _map_pipeline_decision("job-1", unexpected)

    assert outcome == DecisionOutcome("new_fish", "new_fish", False)


def test_unexpected_decision_is_logged_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reaching the fallback means the pipeline broke its contract; it must be visible."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.services.job_service"):
        _map_pipeline_decision("job-1", "nonsense")

    assert any("Unexpected pipeline_decision" in r.message for r in caplog.records)


def test_outcome_is_immutable() -> None:
    """A frozen outcome cannot be mutated after the decision is taken."""
    outcome = _map_pipeline_decision("job-1", "new_fish")

    with pytest.raises(Exception):
        outcome.requires_human_review = True  # type: ignore[misc]


def test_only_repeat_capture_blocks_gallery_writes() -> None:
    """Guards the invariant the persistence branch depends on."""
    review_required = {
        decision: _map_pipeline_decision("job-1", decision).requires_human_review
        for decision in ("auto_match", "new_fish", "repeat_capture")
    }

    assert review_required == {
        "auto_match": False,
        "new_fish": False,
        "repeat_capture": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency payload consistency
# ─────────────────────────────────────────────────────────────────────────────
SIGHTING_COLUMNS = (
    "id",
    "job_id",
    "fish_id",
    "species_slug",
    "confidence",
    "is_new_fish",
    "xp_earned",
    "detection_confidence",
    "classification_confidence",
    "match_confidence",
)


def make_sighting_row(**overrides: object) -> sqlite3.Row:
    """Build a sqlite3.Row shaped like a fish_sightings record."""
    values: dict[str, object] = {
        "id": "sighting-1",
        "job_id": "job-1",
        "fish_id": "CZ-401001-CYPCA-0001",
        "species_slug": "cyprinus_carpio",
        "confidence": 0.93,
        "is_new_fish": 1,
        "xp_earned": 60,
        "detection_confidence": 0.87,
        "classification_confidence": 0.0,
        "match_confidence": 0.0,
    }
    values.update(overrides)

    conn = sqlite3.connect(":memory:")
    try:
        conn.row_factory = sqlite3.Row
        columns = ", ".join(SIGHTING_COLUMNS)
        placeholders = ", ".join("?" for _ in SIGHTING_COLUMNS)
        conn.execute(f"CREATE TABLE s ({columns})")
        conn.execute(
            f"INSERT INTO s ({columns}) VALUES ({placeholders})",
            tuple(values[c] for c in SIGHTING_COLUMNS),
        )
        row = conn.execute("SELECT * FROM s").fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


EXPECTED_KEYS = {
    "status",
    "job_id",
    "fish_id",
    "sighting_id",
    "species_slug",
    "species_english",
    "confidence",
    "is_new_fish",
    "xp_earned",
    "detection_confidence",
    "classification_confidence",
    "match_confidence",
}


def test_skip_result_exposes_the_full_key_set() -> None:
    """
    Both idempotency checks share this builder, so the key set is the contract.
    classification_confidence in particular was missing from the Phase 2 payload.
    """
    result = _build_skip_result("job-1", make_sighting_row())

    assert set(result) == EXPECTED_KEYS


def test_skip_result_reports_completed_when_species_is_known() -> None:
    result = _build_skip_result("job-1", make_sighting_row())

    assert result["status"] == "completed"
    assert result["species_english"]


def test_skip_result_reports_needs_review_without_a_species() -> None:
    result = _build_skip_result("job-1", make_sighting_row(species_slug=None))

    assert result["status"] == "needs_review"
    assert result["species_english"] is None


def test_skip_result_normalises_is_new_fish_to_bool() -> None:
    """SQLite stores it as an integer; the API contract is a boolean."""
    assert _build_skip_result("job-1", make_sighting_row(is_new_fish=1))["is_new_fish"] is True
    assert _build_skip_result("job-1", make_sighting_row(is_new_fish=0))["is_new_fish"] is False


def test_skip_result_uses_the_requested_job_id() -> None:
    result = _build_skip_result("requested-job", make_sighting_row(job_id="stored-job"))

    assert result["job_id"] == "requested-job"


def test_skip_result_maps_row_id_to_sighting_id() -> None:
    result = _build_skip_result("job-1", make_sighting_row(id="abc-123"))

    assert result["sighting_id"] == "abc-123"
    assert "id" not in result
