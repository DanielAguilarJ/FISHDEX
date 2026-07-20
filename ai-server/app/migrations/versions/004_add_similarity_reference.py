"""
Migration 004: Add similarity reference columns for visual evidence traceability.

Tracks which historical capture (embedding/sighting) was the best visual evidence
for an identification decision. Separate from previous_sighting_id (chronological).

Adds columns to:
- identification_jobs: match_reference_* columns
- fish_sightings: match_reference_* columns
- fish_embeddings: sighting_id index (embeddings DB)
"""

import sqlite3
from pathlib import Path

VERSION = 4
NAME = "add_similarity_reference"

# Columns to add to identification_jobs
JOBS_COLUMNS = [
    ("match_reference_fish_id", "TEXT"),
    ("match_reference_sighting_id", "TEXT"),
    ("match_reference_embedding_id", "TEXT"),
    ("match_reference_score", "REAL"),
    ("match_cross_area", "INTEGER DEFAULT 0"),
]

# Columns to add to fish_sightings
SIGHTINGS_COLUMNS = [
    ("match_reference_fish_id", "TEXT"),
    ("match_reference_sighting_id", "TEXT"),
    ("match_reference_embedding_id", "TEXT"),
    ("match_reference_score", "REAL"),
    ("match_cross_area", "INTEGER DEFAULT 0"),
]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    return column in existing


def _get_embeddings_conn() -> sqlite3.Connection:
    """Open a connection to the embeddings database."""
    from app.config import settings

    db_path = Path(settings.embeddings_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def up(conn: sqlite3.Connection) -> None:
    """Add match_reference columns and indexes."""
    # --- Main DB: identification_jobs ---
    if _table_exists(conn, "identification_jobs"):
        for col_name, col_type in JOBS_COLUMNS:
            if not _column_exists(conn, "identification_jobs", col_name):
                conn.execute(
                    f"ALTER TABLE identification_jobs ADD COLUMN {col_name} {col_type}"
                )

    # --- Main DB: fish_sightings ---
    if _table_exists(conn, "fish_sightings"):
        for col_name, col_type in SIGHTINGS_COLUMNS:
            if not _column_exists(conn, "fish_sightings", col_name):
                conn.execute(
                    f"ALTER TABLE fish_sightings ADD COLUMN {col_name} {col_type}"
                )

        # --- Indexes on main DB ---
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sightings_match_reference
            ON fish_sightings(match_reference_sighting_id)
        """)

    if _table_exists(conn, "identification_jobs"):
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_match_reference
            ON identification_jobs(match_reference_sighting_id)
        """)

    conn.commit()

    # --- Embeddings DB: add sighting_id index ---
    try:
        emb_conn = _get_embeddings_conn()
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_sighting_id
            ON fish_embeddings(sighting_id)
        """)
        emb_conn.commit()
        emb_conn.close()
    except Exception:
        # Non-fatal: embeddings DB may not exist yet
        pass


def down(conn: sqlite3.Connection) -> None:
    """Best-effort rollback."""
    conn.execute("DROP INDEX IF EXISTS idx_sightings_match_reference")
    conn.execute("DROP INDEX IF EXISTS idx_jobs_match_reference")

    version = sqlite3.sqlite_version_info
    if version >= (3, 35, 0):
        for col_name, _ in reversed(JOBS_COLUMNS):
            if _column_exists(conn, "identification_jobs", col_name):
                try:
                    conn.execute(
                        f"ALTER TABLE identification_jobs DROP COLUMN {col_name}"
                    )
                except sqlite3.OperationalError:
                    pass
        for col_name, _ in reversed(SIGHTINGS_COLUMNS):
            if _column_exists(conn, "fish_sightings", col_name):
                try:
                    conn.execute(
                        f"ALTER TABLE fish_sightings DROP COLUMN {col_name}"
                    )
                except sqlite3.OperationalError:
                    pass

    conn.commit()

    try:
        emb_conn = _get_embeddings_conn()
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_sighting_id")
        emb_conn.commit()
        emb_conn.close()
    except Exception:
        pass
