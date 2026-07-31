"""
Schema self-sufficiency.

``init_db()`` bootstraps the schema and then runs the versioned migration runner,
but a migration failure is deliberately downgraded to a warning so that legacy
databases still start. That means any column the application writes must exist
*before* migrations run, or the write fails at runtime with "no such column".

26 columns were previously supplied only by migration 001, five of which
(``gps_accuracy_m``, ``gps_timestamp``, ``gps_is_mocked``, ``gps_source``,
``area_selection_source``) are written by ``POST /api/v1/jobs/upload`` on every
single capture. These tests assert the base schema stands on its own.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# Columns written by application code (not by migrations). Keep in sync with the
# INSERT in app/routers/jobs.py::_insert_job_row and the repeat-capture branch of
# app/services/job_service.py.
UPLOAD_COLUMNS = (
    "id",
    "user_id",
    "status",
    "raw_video_filename",
    "area_code",
    "area_name",
    "latitude",
    "longitude",
    "species_slug",
    "notes",
    "weather",
    "bite",
    "size_cm",
    "fish_state",
    "custom_name",
    "created_at",
    "media_type",
    "original_filename",
    "content_type",
    "raw_media_filename",
    "gps_accuracy_m",
    "gps_timestamp",
    "gps_is_mocked",
    "gps_source",
    "area_selection_source",
)

REPEAT_CAPTURE_COLUMNS = (
    "status",
    "updated_at",
    "result_json",
    "match_reference_fish_id",
    "match_reference_sighting_id",
    "match_reference_embedding_id",
    "match_reference_score",
    "match_cross_area",
    "artifact_dir",
    "preview_filename",
)


@pytest.fixture
def bootstrapped_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Create a database with the base schema only, migrations disabled.

    This is the worst-case production state: migration 001 failed and its warning
    was swallowed.
    """
    from app import database

    db_path = tmp_path / "bootstrap.sqlite"
    monkeypatch.setattr(database, "DB_PATH", db_path)

    def refuse_migrations(_conn: sqlite3.Connection) -> None:
        """Stand in for a migration runner that failed."""

    monkeypatch.setattr(database, "_apply_versioned_migrations", refuse_migrations)
    database.init_db()
    return db_path


def columns_of(db_path: Path, table: str) -> set[str]:
    """Return the column names of a table."""
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Column presence
# ─────────────────────────────────────────────────────────────────────────────
def test_upload_columns_exist_without_migrations(bootstrapped_db: Path) -> None:
    present = columns_of(bootstrapped_db, "identification_jobs")
    missing = [c for c in UPLOAD_COLUMNS if c not in present]

    assert missing == [], f"POST /jobs/upload would fail on: {missing}"


def test_repeat_capture_columns_exist_without_migrations(
    bootstrapped_db: Path,
) -> None:
    present = columns_of(bootstrapped_db, "identification_jobs")
    missing = [c for c in REPEAT_CAPTURE_COLUMNS if c not in present]

    assert missing == [], f"the repeat-capture branch would fail on: {missing}"


@pytest.mark.parametrize(
    "table",
    ["users", "identification_jobs", "fish_sightings", "fish_individuals", "user_stats"],
)
def test_every_table_is_created(bootstrapped_db: Path, table: str) -> None:
    assert columns_of(bootstrapped_db, table), f"{table} was not created"


# ─────────────────────────────────────────────────────────────────────────────
# Real writes
# ─────────────────────────────────────────────────────────────────────────────
def test_upload_insert_succeeds_on_the_base_schema(bootstrapped_db: Path) -> None:
    """Exercise the actual INSERT shape rather than only checking column names."""
    conn = sqlite3.connect(bootstrapped_db)
    try:
        placeholders = ", ".join("?" for _ in UPLOAD_COLUMNS)
        conn.execute(
            f"INSERT INTO identification_jobs ({', '.join(UPLOAD_COLUMNS)}) "
            f"VALUES ({placeholders})",
            (
                "job-1",
                "user-1",
                "uploaded",
                "raw_videos/clip.mp4",
                "401001",
                "Test area",
                50.1,
                14.4,
                "cyprinus_carpio",
                None,
                None,
                None,
                None,
                None,
                None,
                "2026-01-01T00:00:00+00:00",
                "video",
                "clip.mp4",
                "video/mp4",
                "raw_videos/clip.mp4",
                5.0,
                "2026-01-01T00:00:00+00:00",
                0,
                "current",
                "user_selected",
            ),
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM identification_jobs").fetchone()[0] == 1
    finally:
        conn.close()


def test_repeat_capture_update_succeeds_on_the_base_schema(
    bootstrapped_db: Path,
) -> None:
    conn = sqlite3.connect(bootstrapped_db)
    try:
        conn.execute(
            "INSERT INTO identification_jobs (id, user_id, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("job-2", "user-1", "processing", "2026-01-01T00:00:00+00:00"),
        )
        assignments = ", ".join(f"{c} = ?" for c in REPEAT_CAPTURE_COLUMNS)
        conn.execute(
            f"UPDATE identification_jobs SET {assignments} WHERE id = ?",
            (
                "repeat_capture",
                "2026-01-01T00:01:00+00:00",
                '{"linkage": {}}',
                None,
                None,
                None,
                None,
                0,
                None,
                None,
                "job-2",
            ),
        )
        conn.commit()
        status = conn.execute(
            "SELECT status FROM identification_jobs WHERE id = ?", ("job-2",)
        ).fetchone()[0]
        assert status == "repeat_capture"
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Per-connection pragmas
# ─────────────────────────────────────────────────────────────────────────────
def test_connections_carry_a_busy_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    busy_timeout is per-connection, not persisted in the database file. It was
    previously only set inside init_db() on a connection that was then closed, so
    every connection handed out ran with busy_timeout=0 and raised SQLITE_BUSY the
    instant a writer held the lock.
    """
    from app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "pragmas.sqlite")
    database.init_db()

    conn = database.get_db_connection()
    try:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()

    assert timeout == database.BUSY_TIMEOUT_MS


def test_connections_enforce_foreign_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """foreign_keys is also per-connection and defaults to OFF."""
    from app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "fk.sqlite")
    database.init_db()

    conn = database.get_db_connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_wal_mode_is_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    WAL is a database property, so unlike the others it survives on a fresh
    connection. It lets readers proceed while a writer holds the lock.
    """
    from app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "wal.sqlite")
    database.init_db()

    conn = database.get_db_connection()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Transactional context manager
# ─────────────────────────────────────────────────────────────────────────────
def test_db_session_commits_on_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "commit.sqlite")
    database.init_db()

    with database.db_session(commit=True) as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("u1", "a@b.c", "x", "A", "fisherman", "2026-01-01T00:00:00+00:00"),
        )

    with database.db_session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_db_session_rolls_back_on_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "rollback.sqlite")
    database.init_db()

    with pytest.raises(RuntimeError):
        with database.db_session(commit=True) as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("u2", "d@e.f", "x", "B", "fisherman", "2026-01-01T00:00:00+00:00"),
            )
            raise RuntimeError("boom")

    with database.db_session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
