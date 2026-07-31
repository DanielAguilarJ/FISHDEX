"""
FishDex AI Server - Local SQLite persistence
============================================
Owns the connection factory and the idempotent schema bootstrap.

Design notes
------------
* ``journal_mode=WAL`` is a *persistent* database property, so it only needs to
  be set once (during :func:`init_db`).
* ``busy_timeout`` and ``foreign_keys`` are **per-connection** pragmas. They
  must therefore be applied in :func:`get_db_connection`, otherwise every
  connection handed out silently falls back to ``busy_timeout=0`` (immediate
  ``SQLITE_BUSY`` under concurrency) and ``foreign_keys=OFF``.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(settings.server_data_dir) / "fishdex_local.sqlite"

# Wait up to 30 s for a competing writer before raising ``SQLITE_BUSY``.
# Background job processing writes concurrently with API reads, so a non-zero
# timeout is required for correctness, not just performance.
BUSY_TIMEOUT_MS = 30_000


def get_db_connection() -> sqlite3.Connection:
    """
    Open a connection to the local SQLite database.

    Applies the per-connection pragmas that SQLite does *not* persist in the
    database file. Callers are responsible for closing the connection; prefer
    :func:`db_session` which does it for you.

    Returns:
        A connection with ``sqlite3.Row`` row factory, a 30 s busy timeout and
        foreign-key enforcement enabled.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    # Per-connection pragmas — NOT inherited from init_db().
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(*, commit: bool = False) -> Iterator[sqlite3.Connection]:
    """
    Context manager that guarantees the connection is closed.

    Args:
        commit: When True, commit on clean exit and roll back on exception.

    Yields:
        An open SQLite connection.

    Example:
        >>> with db_session(commit=True) as conn:
        ...     conn.execute("INSERT INTO users VALUES (...)")
    """
    conn = get_db_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_columns(
    cursor: sqlite3.Cursor,
    table_name: str,
    required_columns: dict[str, str],
) -> None:
    """
    Add any missing columns to ``table_name`` (poor-man's forward migration).

    Args:
        cursor: Open cursor.
        table_name: Table to inspect. Must be a trusted internal constant —
            it is interpolated into DDL, which SQLite cannot parameterise.
        required_columns: Mapping of column name to its SQL type/definition.
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            logger.info(
                "Adding missing column %s.%s %s", table_name, column_name, column_type
            )
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Schema definitions — split per table so each helper stays small and testable
# ─────────────────────────────────────────────────────────────────────────────

_IDENTIFICATION_JOB_COLUMNS: dict[str, str] = {
    "started_at": "TEXT",
    "completed_at": "TEXT",
    "result_sighting_id": "TEXT",
    "result_fish_id": "TEXT",
    "confidence": "REAL",
    "is_new_fish": "INTEGER",
    "xp_earned": "INTEGER",
    "error_message": "TEXT",
    "weather": "TEXT",
    "bite": "TEXT",
    "size_cm": "REAL",
    "fish_state": "TEXT",
    "custom_name": "TEXT",
    "artifact_dir": "TEXT",
    "document_filename": "TEXT",
    "preview_filename": "TEXT",
    "annotated_preview_filename": "TEXT",
    "media_type": "TEXT DEFAULT 'video'",
    "original_filename": "TEXT",
    "content_type": "TEXT",
    "raw_media_filename": "TEXT",
    "video_filename": "TEXT",
    "rarity": "TEXT",
    "detection_confidence": "REAL",
    "classification_confidence": "REAL",
    "match_confidence": "REAL",
    "catch_number": "INTEGER",
    "linked_fish_id": "TEXT",
    "previous_sighting_id": "TEXT",
    "total_sightings_before": "INTEGER DEFAULT 0",
    "total_sightings_after": "INTEGER DEFAULT 1",
    "linkage_json": "TEXT",
    "retry_count": "INTEGER DEFAULT 0",
    # ── Columns the application writes that were previously provided ONLY by
    # migration 001. `_apply_versioned_migrations` downgrades a migration failure
    # to a warning, so on a database where 001 did not run these were absent and
    # the write failed with "no such column" at runtime:
    #   * POST /api/v1/jobs/upload writes all five gps_*/area_selection_source
    #     columns on every capture
    #   * the repeat-capture branch writes result_json and updated_at
    # `_ensure_columns` is idempotent (it consults PRAGMA table_info first) and
    # migration 001 also checks before adding, so declaring them here is safe and
    # makes the base schema self-sufficient.
    "updated_at": "TEXT",
    "result_json": "TEXT",
    "gps_accuracy_m": "REAL",
    "gps_timestamp": "TEXT",
    "gps_is_mocked": "INTEGER DEFAULT 0",
    "gps_source": "TEXT",
    "area_selection_source": "TEXT",
    # Similarity reference (migration 004)
    "match_reference_fish_id": "TEXT",
    "match_reference_sighting_id": "TEXT",
    "match_reference_embedding_id": "TEXT",
    "match_reference_score": "REAL",
    "match_cross_area": "INTEGER DEFAULT 0",
}

_FISH_SIGHTINGS_COLUMNS: dict[str, str] = {
    "area_name": "TEXT",
    "weather": "TEXT",
    "bite": "TEXT",
    "size_cm": "REAL",
    "fish_state": "TEXT",
    "custom_name": "TEXT",
    "notes": "TEXT",
    "artifact_dir": "TEXT",
    "document_filename": "TEXT",
    "preview_filename": "TEXT",
    "annotated_preview_filename": "TEXT",
    "detection_confidence": "REAL",
    "classification_confidence": "REAL",
    "match_confidence": "REAL",
    "catch_number": "INTEGER",
    "media_type": "TEXT DEFAULT 'video'",
    "video_filename": "TEXT",
    "rarity": "TEXT",
    "previous_sighting_id": "TEXT",
    "total_sightings_before": "INTEGER DEFAULT 0",
    "total_sightings_after": "INTEGER DEFAULT 1",
    "linkage_json": "TEXT",
    # Similarity reference (migration 004)
    "match_reference_fish_id": "TEXT",
    "match_reference_sighting_id": "TEXT",
    "match_reference_embedding_id": "TEXT",
    "match_reference_score": "REAL",
    "match_cross_area": "INTEGER DEFAULT 0",
}

_FISH_INDIVIDUALS_COLUMNS: dict[str, str] = {
    "area_name": "TEXT",
    "latest_sighting_id": "TEXT",
    "latest_document_filename": "TEXT",
    "first_sighting_id": "TEXT",
    "reference_frame_filename": "TEXT",
    "max_size_cm": "REAL",
    "last_seen_by": "TEXT",
    "last_seen_lat": "REAL",
    "last_seen_lng": "REAL",
    "first_seen_lat": "REAL",
    "first_seen_lng": "REAL",
    "linkage_updated_at": "TEXT",
}


def _create_users_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``users`` table if absent."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'fisherman',
            created_at TEXT NOT NULL
        )
        """
    )


def _create_identification_jobs_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``identification_jobs`` table and backfill new columns."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS identification_jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            raw_video_filename TEXT,
            area_code TEXT,
            area_name TEXT,
            latitude REAL,
            longitude REAL,
            species_slug TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result_sighting_id TEXT,
            result_fish_id TEXT,
            confidence REAL,
            is_new_fish INTEGER,
            xp_earned INTEGER,
            error_message TEXT
        )
        """
    )
    _ensure_columns(cursor, "identification_jobs", _IDENTIFICATION_JOB_COLUMNS)


def _create_fish_sightings_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``fish_sightings`` table and backfill new columns."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fish_sightings (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            fish_id TEXT NOT NULL,
            job_id TEXT,
            species_slug TEXT,
            species_english TEXT,
            species_czech TEXT,
            species_latin TEXT,
            confidence REAL,
            is_new_fish INTEGER,
            xp_earned INTEGER,
            area_code TEXT,
            frame_filename TEXT,
            raw_video_filename TEXT,
            captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            location_lat REAL,
            location_lng REAL
        )
        """
    )
    _ensure_columns(cursor, "fish_sightings", _FISH_SIGHTINGS_COLUMNS)


def _create_fish_individuals_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``fish_individuals`` table and backfill new columns."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fish_individuals (
            id TEXT PRIMARY KEY,
            fish_id TEXT UNIQUE NOT NULL,
            species_slug TEXT,
            species_english TEXT,
            species_latin TEXT,
            first_seen_by TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            total_sightings INTEGER DEFAULT 1,
            area_code TEXT,
            best_frame_filename TEXT
        )
        """
    )
    _ensure_columns(cursor, "fish_individuals", _FISH_INDIVIDUALS_COLUMNS)


def _create_user_stats_table(cursor: sqlite3.Cursor) -> None:
    """Create the ``user_stats`` table if absent."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_stats (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            total_xp INTEGER DEFAULT 0,
            total_sightings INTEGER DEFAULT 0,
            total_species INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )


def _create_indexes(cursor: sqlite3.Cursor) -> None:
    """Create uniqueness and lookup indexes."""
    statements = (
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fish_sightings_job_id_unique
        ON fish_sightings(job_id)
        WHERE job_id IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fish_sightings_fish_catch_unique
        ON fish_sightings(fish_id, catch_number)
        WHERE fish_id IS NOT NULL AND catch_number IS NOT NULL
        """,
        "CREATE INDEX IF NOT EXISTS idx_fish_sightings_fish_id ON fish_sightings(fish_id)",
        "CREATE INDEX IF NOT EXISTS idx_fish_sightings_user_id ON fish_sightings(user_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_fish_sightings_location
        ON fish_sightings(location_lat, location_lng)
        """,
        "CREATE INDEX IF NOT EXISTS idx_identification_jobs_status ON identification_jobs(status)",
        # Job listing is always ordered by creation date in the dashboard.
        "CREATE INDEX IF NOT EXISTS idx_identification_jobs_created_at ON identification_jobs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_identification_jobs_user_id ON identification_jobs(user_id)",
        # Login path: lookup by email on every authentication request.
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    )
    for statement in statements:
        cursor.execute(statement)


def _apply_versioned_migrations(conn: sqlite3.Connection) -> None:
    """
    Run the versioned migration runner, tolerating pre-existing databases.

    A migration failure is logged as a warning rather than raised because
    legacy databases may already contain the target schema.
    """
    try:
        from app.migrations.runner import run_migrations

        final_version = run_migrations(conn)
        logger.info("Migrations applied up to version %d", final_version)
    except Exception as exc:  # noqa: BLE001 — a migration failure must not stop a legacy DB from starting
        logger.warning(
            "Migration runner failed (non-fatal for existing DBs): %s", exc, exc_info=True
        )


def init_db() -> None:
    """
    Create the schema if it does not exist and apply versioned migrations.

    Idempotent: safe to call on every process start.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection()
    try:
        # WAL is persisted in the database header, so setting it once is enough.
        conn.execute("PRAGMA journal_mode = WAL")

        cursor = conn.cursor()
        _create_users_table(cursor)
        _create_identification_jobs_table(cursor)
        _create_fish_sightings_table(cursor)
        _create_fish_individuals_table(cursor)
        _create_user_stats_table(cursor)
        _create_indexes(cursor)
        conn.commit()

        _apply_versioned_migrations(conn)
    finally:
        conn.close()

    logger.info("Local SQLite database initialized at %s", DB_PATH.resolve())
