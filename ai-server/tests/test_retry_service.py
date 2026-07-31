"""
Background crop-retry service.

When the detector finds nothing usable in a capture, the job is parked as
``pending_crop`` and this service retries it with progressively looser thresholds.
It is the last chance to rescue a capture the angler already took, so the failure
modes matter: a job that gets stuck here is a lost capture, and a job that escapes
the retry ceiling is an infinite loop against the GPU.

This is where the audit found a call to an undefined ``_mark_manual_review``, which
raised ``NameError`` whenever the raw media file was missing and left the job in
``pending_crop`` forever. Those state transitions are pinned here.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from app import database
from app.services import retry_service
from app.services.retry_service import (
    RETRY_CONFIGS,
    _increment_retry,
    _is_valid_tight,
    _mark_failed_retries,
    _mark_missing_media,
    _reset_job_for_full_pipeline,
)

SCHEMA = """
CREATE TABLE identification_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    completed_at TEXT,
    preview_filename TEXT,
    raw_media_filename TEXT,
    media_type TEXT,
    created_at TEXT
);
"""


@dataclass
class FakeDetection:
    """Detection stand-in exposing the attributes the validator reads."""

    confidence: float
    polygon: list | None


def square_polygon(side: float, origin: float = 0.0) -> list:
    """Build an axis-aligned square polygon of the given side length."""
    return [
        (origin, origin),
        (origin + side, origin),
        (origin + side, origin + side),
        (origin, origin + side),
    ]


@pytest.fixture
def retry_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated database and route the service's connections to it."""
    path = tmp_path / "retry.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    monkeypatch.setattr(retry_service, "get_db_connection", get_test_connection)
    return path


def insert_job(db_path: Path, job_id: str, status: str, retry_count: int = 0) -> None:
    """Insert a job row."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO identification_jobs "
            "(id, user_id, status, retry_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "user-1", status, retry_count, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def read_job(db_path: Path, job_id: str) -> dict:
    """Read a job row as a dict."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM identification_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# Retry ladder
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_configs_loosen_progressively() -> None:
    """
    Each attempt must be at least as permissive as the previous one, or a later
    attempt could reject what an earlier one accepted — making the retry pointless.
    """
    confidences = [conf for conf, _ in RETRY_CONFIGS]

    assert confidences == sorted(confidences, reverse=True)


def test_retry_configs_stay_within_sane_bounds() -> None:
    for confidence, max_area in RETRY_CONFIGS:
        assert 0.0 < confidence < 1.0
        assert 0.0 < max_area <= 1.0


def test_retry_ladder_is_bounded() -> None:
    """An unbounded ladder would retry a hopeless capture against the GPU forever."""
    assert 1 <= len(RETRY_CONFIGS) <= 5


# ─────────────────────────────────────────────────────────────────────────────
# Detection validation
# ─────────────────────────────────────────────────────────────────────────────
def test_none_detection_is_rejected() -> None:
    assert _is_valid_tight(None, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_low_confidence_is_rejected() -> None:
    detection = FakeDetection(confidence=0.1, polygon=square_polygon(200))

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_confidence_at_the_threshold_is_accepted() -> None:
    """Boundary inclusive: the ladder's lowest rung must actually admit something."""
    detection = FakeDetection(confidence=0.2, polygon=square_polygon(200))

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is True


def test_missing_polygon_is_rejected() -> None:
    """The retry path crops from the OBB polygon, so a bbox alone is unusable."""
    detection = FakeDetection(confidence=0.9, polygon=None)

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_degenerate_polygon_is_rejected() -> None:
    detection = FakeDetection(confidence=0.9, polygon=[(0, 0), (1, 0)])

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_a_detection_covering_almost_the_whole_frame_is_rejected() -> None:
    """
    A near-full-frame box means the detector locked onto the background, not the
    fish. Cropping it would embed the scene rather than the animal.
    """
    detection = FakeDetection(confidence=0.9, polygon=square_polygon(470))

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_a_tiny_detection_is_rejected() -> None:
    """Below 0.1% of the frame there is not enough pattern to identify anything."""
    detection = FakeDetection(confidence=0.9, polygon=square_polygon(4))

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is False


def test_a_reasonable_detection_is_accepted() -> None:
    detection = FakeDetection(confidence=0.5, polygon=square_polygon(300))

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is True


def test_a_zero_area_frame_is_rejected_without_dividing_by_zero() -> None:
    detection = FakeDetection(confidence=0.9, polygon=square_polygon(10))

    assert _is_valid_tight(detection, (0, 0), min_conf=0.2, max_area=0.65) is False


def test_a_looser_max_area_admits_a_larger_detection() -> None:
    """The ladder's purpose: what rung 1 rejects, rung 3 may accept."""
    detection = FakeDetection(confidence=0.9, polygon=square_polygon(430))
    frame = (480, 640)

    strict = _is_valid_tight(detection, frame, min_conf=0.2, max_area=0.60)
    loose = _is_valid_tight(detection, frame, min_conf=0.2, max_area=0.75)

    assert strict is False
    assert loose is True


def test_validation_accepts_a_numpy_polygon() -> None:
    """Detections arrive with numpy coordinates from the detector."""
    polygon = np.array(square_polygon(300), dtype=np.float32).tolist()
    detection = FakeDetection(confidence=0.5, polygon=polygon)

    assert _is_valid_tight(detection, (480, 640), min_conf=0.2, max_area=0.65) is True


# ─────────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_media_terminates_the_job(retry_db: Path) -> None:
    """
    The regression this covers: the original code called an undefined
    _mark_manual_review here, raising NameError and leaving the job in
    pending_crop forever.
    """
    insert_job(retry_db, "job-gone", "pending_crop")

    _mark_missing_media("job-gone")

    job = read_job(retry_db, "job-gone")
    assert job["status"] == "failed"
    assert "missing" in job["error_message"].lower()


def test_missing_media_stops_further_retries(retry_db: Path) -> None:
    """Retrying without the source file can never succeed, so the count is capped."""
    insert_job(retry_db, "job-gone", "pending_crop")

    _mark_missing_media("job-gone")

    assert read_job(retry_db, "job-gone")["retry_count"] == 3


def test_exhausted_retries_mark_the_job_failed(retry_db: Path) -> None:
    insert_job(retry_db, "job-done", "pending_crop", retry_count=3)

    _mark_failed_retries("job-done")

    job = read_job(retry_db, "job-done")
    assert job["status"] == "failed"
    assert "retries exhausted" in job["error_message"].lower()


def test_increment_advances_the_retry_count(retry_db: Path) -> None:
    insert_job(retry_db, "job-a", "pending_crop", retry_count=1)

    _increment_retry("job-a", 1)

    assert read_job(retry_db, "job-a")["retry_count"] == 2


def test_reset_moves_a_pending_crop_job_back_to_uploaded(retry_db: Path) -> None:
    """A successful retry hands the job back to the full pipeline."""
    insert_job(retry_db, "job-b", "pending_crop", retry_count=0)

    assert _reset_job_for_full_pipeline("job-b", 0) is True

    job = read_job(retry_db, "job-b")
    assert job["status"] == "uploaded"
    assert job["retry_count"] == 1
    assert job["error_message"] is None


def test_reset_clears_the_stale_preview_and_completion(retry_db: Path) -> None:
    """
    Leaving the previous attempt's preview behind would show the operator an
    artifact from a run that produced no identity.
    """
    conn = sqlite3.connect(retry_db)
    try:
        conn.execute(
            "INSERT INTO identification_jobs (id, user_id, status, retry_count, "
            "preview_filename, completed_at, error_message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-c",
                "user-1",
                "pending_crop",
                0,
                "stale.jpg",
                "2026-01-01T00:00:00+00:00",
                "previous failure",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _reset_job_for_full_pipeline("job-c", 0)

    job = read_job(retry_db, "job-c")
    assert job["preview_filename"] is None
    assert job["completed_at"] is None
    assert job["error_message"] is None


def test_reset_refuses_a_job_in_another_status(retry_db: Path) -> None:
    """
    The UPDATE filters on status='pending_crop', so a job already claimed by the
    main pipeline cannot be yanked back mid-processing.
    """
    insert_job(retry_db, "job-d", "processing")

    assert _reset_job_for_full_pipeline("job-d", 0) is False
    assert read_job(retry_db, "job-d")["status"] == "processing"


def test_reset_of_an_unknown_job_reports_failure(retry_db: Path) -> None:
    assert _reset_job_for_full_pipeline("job-absent", 0) is False


def test_transitions_survive_a_missing_row(retry_db: Path) -> None:
    """
    Called from a background loop, so a row deleted between scan and update must
    not raise and kill the loop.
    """
    _mark_missing_media("never-existed")
    _mark_failed_retries("never-existed")
    _increment_retry("never-existed", 0)
