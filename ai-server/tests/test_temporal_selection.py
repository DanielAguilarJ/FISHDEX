"""
Temporal diversity selection (temporal NMS).

The algorithm existed twice: once as ``_select_with_temporal_diversity`` and once
reimplemented inline in ``process_identification_job``, which needed indices
rather than objects and used a throwaway ``_MetaWrapper`` class to get them. The
copies could drift, and had already: the inline version omitted the
``max_count``/``min_gap`` clamping.

Both paths now share ``select_indices_with_temporal_diversity``. These tests pin
the algorithm's contract and assert the two entry points agree.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.job_service import (
    _select_with_temporal_diversity,
    select_indices_with_temporal_diversity,
)


@dataclass
class Scored:
    """Minimal object satisfying the TemporallyScored protocol."""

    score: float
    frame_index: int
    timestamp_seconds: float


def make(*specs: tuple[float, int, float]) -> list[Scored]:
    """Build candidates from (score, frame_index, timestamp) triples."""
    return [Scored(score=s, frame_index=i, timestamp_seconds=t) for s, i, t in specs]


# ─────────────────────────────────────────────────────────────────────────────
# Ranking
# ─────────────────────────────────────────────────────────────────────────────
def test_highest_score_is_selected_first() -> None:
    items = make((0.2, 0, 0.0), (0.9, 1, 5.0), (0.5, 2, 10.0))

    assert select_indices_with_temporal_diversity(items, max_count=3)[0] == 1


def test_frame_index_breaks_score_ties_deterministically() -> None:
    """Equal scores must resolve by frame index, so runs are reproducible."""
    items = make((0.7, 5, 0.0), (0.7, 2, 5.0), (0.7, 9, 10.0))

    assert select_indices_with_temporal_diversity(items, max_count=3) == [1, 0, 2]


def test_max_count_is_respected() -> None:
    items = make(*[(0.9 - i * 0.01, i, i * 2.0) for i in range(10)])

    assert len(select_indices_with_temporal_diversity(items, max_count=4)) == 4


# ─────────────────────────────────────────────────────────────────────────────
# Temporal spacing
# ─────────────────────────────────────────────────────────────────────────────
def test_frames_closer_than_the_gap_are_rejected() -> None:
    """Two near-simultaneous frames show the same view; only one is useful."""
    items = make((0.9, 0, 1.00), (0.8, 1, 1.05), (0.7, 2, 9.00))

    selected = select_indices_with_temporal_diversity(
        items, max_count=3, min_gap_seconds=0.30
    )

    assert selected == [0, 2]


def test_no_backfill_with_near_duplicates() -> None:
    """
    Asked for 5 but only 2 are sufficiently distinct: return 2.

    Padding would hand the multiframe vote several copies of one view, inflating
    apparent agreement without adding evidence.
    """
    items = make(
        (0.9, 0, 1.00),
        (0.8, 1, 1.01),
        (0.7, 2, 1.02),
        (0.6, 3, 8.00),
        (0.5, 4, 8.01),
    )

    assert len(select_indices_with_temporal_diversity(items, max_count=5)) == 2


def test_zero_gap_disables_temporal_filtering() -> None:
    items = make((0.9, 0, 1.0), (0.8, 1, 1.0), (0.7, 2, 1.0))

    selected = select_indices_with_temporal_diversity(
        items, max_count=3, min_gap_seconds=0.0
    )

    assert len(selected) == 3


def test_gap_is_measured_against_every_selection_not_just_the_last() -> None:
    """
    A frame must clear the gap from *all* prior picks. Comparing only against the
    most recent selection would admit clusters.
    """
    items = make((0.9, 0, 0.0), (0.8, 1, 5.0), (0.7, 2, 0.1))

    selected = select_indices_with_temporal_diversity(
        items, max_count=3, min_gap_seconds=1.0
    )

    assert selected == [0, 1]


# ─────────────────────────────────────────────────────────────────────────────
# Guards
# ─────────────────────────────────────────────────────────────────────────────
def test_empty_input_returns_empty() -> None:
    assert select_indices_with_temporal_diversity([]) == []


@pytest.mark.parametrize("bad_max", [0, -1, -100])
def test_max_count_is_clamped_to_at_least_one(bad_max: int) -> None:
    """
    The inline copy lacked this clamp. A non-positive max_count must still yield
    one frame rather than silently selecting nothing and failing downstream.
    """
    items = make((0.9, 0, 0.0), (0.8, 1, 5.0))

    assert len(select_indices_with_temporal_diversity(items, max_count=bad_max)) == 1


def test_negative_gap_is_clamped_to_zero() -> None:
    items = make((0.9, 0, 1.0), (0.8, 1, 1.0))

    selected = select_indices_with_temporal_diversity(
        items, max_count=2, min_gap_seconds=-5.0
    )

    assert len(selected) == 2


def test_indices_are_valid_and_unique() -> None:
    items = make(*[(0.9 - i * 0.05, i, i * 1.5) for i in range(8)])

    selected = select_indices_with_temporal_diversity(items, max_count=5)

    assert len(set(selected)) == len(selected)
    assert all(0 <= i < len(items) for i in selected)


# ─────────────────────────────────────────────────────────────────────────────
# Equivalence of the two entry points
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("max_count", [1, 2, 3, 5, 10])
@pytest.mark.parametrize("min_gap", [0.0, 0.3, 1.0, 5.0])
def test_object_and_index_paths_agree(max_count: int, min_gap: float) -> None:
    """The wrapper must return exactly the items the index path selects."""
    items = make(
        (0.95, 0, 0.00),
        (0.90, 1, 0.20),
        (0.85, 2, 1.50),
        (0.80, 3, 1.60),
        (0.75, 4, 4.00),
        (0.70, 5, 8.00),
    )

    by_index = select_indices_with_temporal_diversity(
        items, max_count=max_count, min_gap_seconds=min_gap
    )
    by_object = _select_with_temporal_diversity(
        items, max_count=max_count, min_gap_seconds=min_gap
    )

    assert by_object == [items[i] for i in by_index]
