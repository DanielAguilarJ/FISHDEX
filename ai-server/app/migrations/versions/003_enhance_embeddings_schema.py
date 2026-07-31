"""
Migration 003: Enhance embeddings database schema.

Adds metadata columns to fish_embeddings and creates indexes for
efficient lookups by species/model and fish/model combinations.

NOTE: This migration targets the embeddings database (settings.embeddings_db_path),
not the main application database. The runner applies it to the main DB's
schema_migrations for tracking, but the DDL executes against the embeddings DB.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION = 3
NAME = "enhance_embeddings_schema"

COLUMNS = [
    ("dimensions", "INTEGER"),
    ("quality_score", "REAL"),
    ("frame_index", "INTEGER"),
    ("vector_type", "TEXT DEFAULT 'prototype'"),
    ("gps_accuracy_m", "REAL"),
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


def up(conn: sqlite3.Connection) -> None:
    """Add metadata columns and indexes to fish_embeddings."""
    emb_conn = _get_embeddings_conn()
    try:
        # Check that fish_embeddings table exists
        cursor = emb_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fish_embeddings'"
        )
        if not cursor.fetchone():
            # Table doesn't exist yet — create it now so columns and indexes
            # are ready when the embedding service starts storing data.
            emb_conn.execute("""
                CREATE TABLE fish_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fish_id TEXT NOT NULL,
                    sighting_id TEXT,
                    species_slug TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    area_code TEXT,
                    embedding BLOB NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    created_at TEXT DEFAULT (datetime('now')),
                    dimensions INTEGER,
                    quality_score REAL,
                    frame_index INTEGER,
                    vector_type TEXT DEFAULT 'prototype',
                    gps_accuracy_m REAL
                )
            """)
            emb_conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_species_model
                ON fish_embeddings(species_slug, model_version)
            """)
            emb_conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_fish_model
                ON fish_embeddings(fish_id, model_version)
            """)
            emb_conn.commit()
            return

        for col_name, col_type in COLUMNS:
            if not _column_exists(emb_conn, "fish_embeddings", col_name):
                emb_conn.execute(
                    f"ALTER TABLE fish_embeddings ADD COLUMN {col_name} {col_type}"
                )

        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_species_model
            ON fish_embeddings(species_slug, model_version)
        """)
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_fish_model
            ON fish_embeddings(fish_id, model_version)
        """)

        emb_conn.commit()
    finally:
        emb_conn.close()


def down(conn: sqlite3.Connection) -> None:
    """Best-effort rollback of embeddings schema changes."""
    try:
        emb_conn = _get_embeddings_conn()
    except Exception as exc:  # noqa: BLE001 — rollback is best-effort
        logger.warning("Embeddings DB unavailable, skipping rollback: %s", exc)
        return

    try:
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_fish_model")
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_species_model")

        version = sqlite3.sqlite_version_info
        if version >= (3, 35, 0):
            for col_name, _ in reversed(COLUMNS):
                if _column_exists(emb_conn, "fish_embeddings", col_name):
                    try:
                        emb_conn.execute(
                            f"ALTER TABLE fish_embeddings DROP COLUMN {col_name}"
                        )
                    except sqlite3.OperationalError:
                        pass

        emb_conn.commit()
    finally:
        emb_conn.close()
