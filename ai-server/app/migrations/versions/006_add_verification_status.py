"""
Migration 006: Add verification_status column to fish_embeddings.

Targets the embeddings database (settings.embeddings_db_path).

Purpose:
    Prevents gallery contamination by tracking the provenance and trust level
    of each embedding. Only 'anchor_new' and 'human_confirmed' embeddings
    should be used as gallery supports for identification.

Values:
    - anchor_new: First sighting of a definitively new fish
    - human_confirmed: Recapture confirmed by human review
    - auto_match_unverified: Auto-matched but not yet human-verified
    - legacy_untrusted: Pre-migration data with unknown provenance
"""

import sqlite3
from pathlib import Path

VERSION = 6
NAME = "add_verification_status"


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


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return column in {row[1] for row in cursor.fetchall()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def up(conn: sqlite3.Connection) -> None:
    """Add verification_status column and migrate existing data."""
    emb_conn = _get_embeddings_conn()
    try:
        if not _table_exists(emb_conn, "fish_embeddings"):
            # Table doesn't exist yet — will be created by migration 005
            return

        if not _column_exists(emb_conn, "fish_embeddings", "verification_status"):
            # Add column with default 'legacy_untrusted' for existing rows
            emb_conn.execute("""
                ALTER TABLE fish_embeddings
                ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'legacy_untrusted'
            """)

        # Create index for fast gallery queries filtered by status
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_verification_status
            ON fish_embeddings(verification_status)
        """)

        # Composite index: the primary query path for candidate retrieval
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_species_model_status
            ON fish_embeddings(species_slug, model_version, verification_status)
        """)

        emb_conn.commit()
    finally:
        emb_conn.close()


def down(conn: sqlite3.Connection) -> None:
    """Best-effort rollback — drop indexes (can't drop column in SQLite)."""
    try:
        emb_conn = _get_embeddings_conn()
    except Exception:
        return

    try:
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_verification_status")
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_species_model_status")
        emb_conn.commit()
    finally:
        emb_conn.close()
