"""
Characterization tests for the job preparation phase.

``process_identification_job`` is ~1290 lines and only 11% covered, so its
early steps are pinned here **before** they are extracted into helpers. These
tests describe observable behaviour — return payloads and database state — not
implementation, so they stay valid across the refactor.

Covered:
  Step 0  idempotency: a job that already produced a sighting is not reprocessed
  Step 2  status validation: completed / processing / failed handling
  Step 3  atomic claim: only one worker may transition a job to 'processing'
  Step 4  media resolution: missing filename and missing file on disk
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import database

SCHEMA = """
CREATE TABLE identification_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_video_filename TEXT,
    raw_media_filename TEXT,
    media_type TEXT,
    content_type TEXT,
    area_code TEXT,
    latitude REAL,
    longitude REAL,
    species_slug TEXT,
    created_at TEXT,
    started_at TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);
CREATE TABLE fish_sightings (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    job_id TEXT,
    fish_id TEXT,
    species_slug TEXT,
    confidence REAL,
    is_new_fish INTEGER,
    xp_earned INTEGER,
    detection_confidence REAL,
    classification_confidence REAL,
    match_confidence REAL
);
CREATE TABLE fish_individuals (
    id TEXT PRIMARY KEY,
    fish_id TEXT UNIQUE,
    total_sightings INTEGER DEFAULT 1
);
CREATE TABLE user_stats (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE,
    total_xp INTEGER DEFAULT 0,
    total_sightings INTEGER DEFAULT 0,
    total_species INTEGER DEFAULT 0,
    updated_at TEXT
);
"""


@pytest.fixture
def job_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated database and route the service's connections to it."""
    path = tmp_path / "jobs.sqlite"
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

    # job_service imports get_db_connection directly, so patch both bindings.
    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    from app.services import job_service

    monkeypatch.setattr(job_service, "get_db_connection", get_test_connection)
    return path


def insert_job(db_path: Path, job_id: str, status: str, **overrides: object) -> None:
    """Insert a job row with sensible defaults."""
    row = {
        "id": job_id,
        "user_id": "user-1",
        "status": status,
        "raw_media_filename": "raw_videos/clip.mp4",
        "media_type": "video",
        "species_slug": "cyprinus_carpio",
        "latitude": 50.1,
        "longitude": 14.4,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(overrides)  # type: ignore[arg-type]
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO identification_jobs ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()


def insert_sighting(db_path: Path, job_id: str, **overrides: object) -> None:
    """Insert a completed sighting linked to a job."""
    row = {
        "id": f"sighting-for-{job_id}",
        "user_id": "user-1",
        "job_id": job_id,
        "fish_id": "CZ-401001-CYPCA-0001",
        "species_slug": "cyprinus_carpio",
        "confidence": 0.91,
        "is_new_fish": 1,
        "xp_earned": 60,
        "detection_confidence": 0.88,
        "classification_confidence": 0.0,
        "match_confidence": 0.0,
    }
    row.update(overrides)  # type: ignore[arg-type]
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO fish_sightings ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()


def read_status(db_path: Path, job_id: str) -> str:
    """Return a job's current status."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status FROM identification_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


def run_job(job_id: str, **kwargs: object) -> dict:
    """Invoke the processor under test."""
    from app.services.job_service import process_identification_job

    return process_identification_job(job_id, **kwargs)  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — idempotency
# ─────────────────────────────────────────────────────────────────────────────
def test_existing_sighting_short_circuits_processing(job_db: Path) -> None:
    """A job that already produced a sighting must not be reprocessed."""
    insert_job(job_db, "job-done", "completed")
    insert_sighting(job_db, "job-done")

    result = run_job("job-done")

    assert result["status"] == "completed"
    assert result["job_id"] == "job-done"
    assert result["fish_id"] == "CZ-401001-CYPCA-0001"
    assert result["sighting_id"] == "sighting-for-job-done"
    assert result["is_new_fish"] is True
    assert result["xp_earned"] == 60


def test_existing_sighting_without_species_reports_needs_review(job_db: Path) -> None:
    insert_job(job_db, "job-nospecies", "completed")
    insert_sighting(job_db, "job-nospecies", species_slug=None)

    result = run_job("job-nospecies")

    assert result["status"] == "needs_review"
    assert result["species_slug"] is None


def test_idempotency_check_leaves_status_untouched(job_db: Path) -> None:
    """The short-circuit path must not mutate the job row."""
    insert_job(job_db, "job-done", "completed")
    insert_sighting(job_db, "job-done")

    run_job("job-done")

    assert read_status(job_db, "job-done") == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1/2 — lookup and status validation
# ─────────────────────────────────────────────────────────────────────────────
def test_unknown_job_raises_value_error(job_db: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        run_job("does-not-exist")


def test_completed_job_without_sighting_requires_force(job_db: Path) -> None:
    insert_job(job_db, "job-completed", "completed")

    with pytest.raises(ValueError, match="already completed"):
        run_job("job-completed")


def test_job_already_processing_exits_gracefully(job_db: Path) -> None:
    """
    Concurrency guard: a second worker must return rather than raise, so the
    caller does not retry a job that is already in flight.
    """
    insert_job(job_db, "job-inflight", "processing")

    result = run_job("job-inflight")

    assert result["status"] == "already_processing"
    assert result["job_id"] == "job-inflight"


def test_previously_failed_job_requires_force(job_db: Path) -> None:
    insert_job(job_db, "job-failed", "failed")

    with pytest.raises(ValueError, match="previously failed"):
        run_job("job-failed")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — atomic claim
# ─────────────────────────────────────────────────────────────────────────────
def test_claim_fails_when_status_is_not_claimable(job_db: Path) -> None:
    """
    With force=True the status checks are bypassed, but the atomic UPDATE still
    filters on status IN ('uploaded','pending_crop'). A job in another state
    therefore cannot be claimed, and the function must report that instead of
    proceeding with a half-claimed job.
    """
    insert_job(job_db, "job-weird", "needs_manual_review")

    result = run_job("job-weird", force=True)

    assert result["status"] == "already_processing"
    assert read_status(job_db, "job-weird") == "needs_manual_review"


@pytest.mark.parametrize("claimable_status", ["uploaded", "pending_crop"])
def test_claimable_statuses_transition_to_processing(
    job_db: Path, claimable_status: str
) -> None:
    """
    Both claimable statuses must be accepted. Processing then fails at Step 4
    because no media file exists, which is the expected outcome here — the point
    is that the claim itself succeeded.
    """
    insert_job(job_db, "job-claim", claimable_status, raw_media_filename=None)

    with pytest.raises(ValueError, match="no raw media filename"):
        run_job("job-claim")

    # The claim is committed before Step 4 runs, so the row stays in 'processing'.
    assert read_status(job_db, "job-claim") == "processing"


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — media resolution
# ─────────────────────────────────────────────────────────────────────────────
def test_missing_media_filename_raises(job_db: Path) -> None:
    insert_job(job_db, "job-nofile", "uploaded", raw_media_filename=None)

    with pytest.raises(ValueError, match="no raw media filename"):
        run_job("job-nofile")


def test_missing_file_on_disk_raises_file_not_found(job_db: Path) -> None:
    insert_job(
        job_db, "job-gone", "uploaded", raw_media_filename="raw_videos/absent.mp4"
    )

    with pytest.raises(FileNotFoundError, match="not found on disk"):
        run_job("job-gone")


def test_legacy_raw_video_filename_column_is_honoured(job_db: Path) -> None:
    """
    Older rows populated raw_video_filename instead of raw_media_filename; both
    must resolve.
    """
    insert_job(
        job_db,
        "job-legacy",
        "uploaded",
        raw_media_filename=None,
        raw_video_filename="raw_videos/legacy.mp4",
    )

    with pytest.raises(FileNotFoundError, match="legacy.mp4"):
        run_job("job-legacy")


# ─────────────────────────────────────────────────────────────────────────────
# Step 9 — species resolution
# ─────────────────────────────────────────────────────────────────────────────
# Species is never inferred: the detector is binary and the angler confirms it.
# A bad slug must therefore abort the job rather than fall back to a guess, since
# the candidate gallery is partitioned by species and a wrong partition would
# compare a carp against pike embeddings.


def test_species_resolution_returns_canonical_catalog_entry() -> None:
    from app.services.job_service import _resolve_confirmed_species

    info = _resolve_confirmed_species("job-1", "cyprinus_carpio")

    assert info["slug"] == "cyprinus_carpio"
    assert info.get("english_name")


def test_species_resolution_canonicalises_surrounding_whitespace() -> None:
    from app.services.job_service import _resolve_confirmed_species

    assert (
        _resolve_confirmed_species("job-1", "  cyprinus_carpio  ")["slug"]
        == "cyprinus_carpio"
    )


@pytest.mark.parametrize("bad_slug", [None, "", "   ", 42, [], {}])
def test_species_resolution_rejects_missing_slug(bad_slug: object) -> None:
    from app.services.job_service import _resolve_confirmed_species

    with pytest.raises(ValueError, match="without a selected species_slug"):
        _resolve_confirmed_species("job-1", bad_slug)


def test_species_resolution_rejects_unknown_slug() -> None:
    from app.services.job_service import _resolve_confirmed_species

    with pytest.raises(ValueError, match="invalid species_slug"):
        _resolve_confirmed_species("job-1", "loch_ness_monster")


def test_species_resolution_never_guesses_on_a_typo() -> None:
    """A near-miss must fail loudly, not fuzzy-match onto the wrong species."""
    from app.services.job_service import _resolve_confirmed_species

    with pytest.raises(ValueError, match="invalid species_slug"):
        _resolve_confirmed_species("job-1", "cyprinus_carpi")


# ─────────────────────────────────────────────────────────────────────────────
# Local sentinels
# ─────────────────────────────────────────────────────────────────────────────
def test_no_dir_based_local_variable_probing() -> None:
    """
    Six call sites used ``'name' in dir()`` to test whether a local had been
    assigned. That silently reports False from any nested scope, so the guards
    are now explicit None/default sentinels. This test keeps the idiom from
    coming back.
    """
    import inspect

    from app.services import job_service

    source = inspect.getsource(job_service)
    offending = [
        line.strip()
        for line in source.splitlines()
        if "in dir()" in line and not line.strip().startswith("#")
    ]
    assert offending == [], f"dir()-based local probing reintroduced: {offending}"


def test_claimable_statuses_is_the_single_source_of_truth() -> None:
    """
    The status guard and the atomic UPDATE previously duplicated the claimable
    status tuple — one as an if-chain, one as a hardcoded SQL IN clause. They now
    share a constant so they cannot drift apart.
    """
    from app.services.job_service import CLAIMABLE_STATUSES

    assert CLAIMABLE_STATUSES == ("uploaded", "pending_crop")
