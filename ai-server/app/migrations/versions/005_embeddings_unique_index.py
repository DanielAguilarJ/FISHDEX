"""
Migration 005: Add UNIQUE index for embedding idempotency + fix id type.

Targets the embeddings database (settings.embeddings_db_path).

Changes:
1. If fish_embeddings.id is INTEGER (from migration 003 on fresh install),
   recreate the table with id TEXT PRIMARY KEY to match matching_service.py
   which inserts UUID strings.
2. Add UNIQUE index on (sighting_id, model_version, vector_type) to guarantee
   idempotent rebuild via INSERT ... ON CONFLICT DO NOTHING.
3. Add sighting_id index if missing.
"""

import sqlite3
from pathlib import Path

VERSION = 5
NAME = "embeddings_unique_index"


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
    """Report whether a column exists on a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return column in {row[1] for row in cursor.fetchall()}


def _id_column_is_integer(conn: sqlite3.Connection) -> bool:
    """Check if fish_embeddings.id is INTEGER (needs migration to TEXT)."""
    cursor = conn.execute("PRAGMA table_info(fish_embeddings)")
    for row in cursor.fetchall():
        if row[1] == "id" and row[2].upper() == "INTEGER":
            return True
    return False


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Report whether a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def up(conn: sqlite3.Connection) -> None:
    """Fix id type and add UNIQUE idempotency index."""
    emb_conn = _get_embeddings_conn()
    try:
        if not _table_exists(emb_conn, "fish_embeddings"):
            # Create the table from scratch with correct schema.
            emb_conn.execute("""
                CREATE TABLE fish_embeddings (
                    id TEXT PRIMARY KEY,
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
        elif _id_column_is_integer(emb_conn):
            # Recreate table with id TEXT PRIMARY KEY, preserving all data.
            # SQLite does not support ALTER COLUMN, so we use the
            # rename-create-copy-drop pattern.
            emb_conn.execute("ALTER TABLE fish_embeddings RENAME TO _fish_embeddings_old")

            emb_conn.execute("""
                CREATE TABLE fish_embeddings (
                    id TEXT PRIMARY KEY,
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

            # Copy data, casting INTEGER id to TEXT.
            emb_conn.execute("""
                INSERT INTO fish_embeddings (
                    id, fish_id, sighting_id, species_slug, model_version,
                    area_code, embedding, latitude, longitude, created_at,
                    dimensions, quality_score, frame_index, vector_type, gps_accuracy_m
                )
                SELECT
                    CAST(id AS TEXT), fish_id, sighting_id, species_slug, model_version,
                    area_code, embedding, latitude, longitude, created_at,
                    dimensions, quality_score, frame_index, vector_type, gps_accuracy_m
                FROM _fish_embeddings_old
            """)

            emb_conn.execute("DROP TABLE _fish_embeddings_old")

        # Ensure columns exist (in case migration 003 was skipped).
        for col_name, col_type in [
            ("dimensions", "INTEGER"),
            ("quality_score", "REAL"),
            ("frame_index", "INTEGER"),
            ("vector_type", "TEXT DEFAULT 'prototype'"),
            ("gps_accuracy_m", "REAL"),
        ]:
            if not _column_exists(emb_conn, "fish_embeddings", col_name):
                emb_conn.execute(
                    f"ALTER TABLE fish_embeddings ADD COLUMN {col_name} {col_type}"
                )

        # Indexes from migration 003.
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_species_model
            ON fish_embeddings(species_slug, model_version)
        """)
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_fish_model
            ON fish_embeddings(fish_id, model_version)
        """)
        emb_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_sighting_id
            ON fish_embeddings(sighting_id)
        """)

        # UNIQUE index for rebuild idempotency.
        # Allows INSERT ... ON CONFLICT(sighting_id, model_version, vector_type) DO NOTHING.
        emb_conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_sighting_model_vector
            ON fish_embeddings(sighting_id, model_version, vector_type)
        """)

        emb_conn.commit()
    finally:
        emb_conn.close()


def down(conn: sqlite3.Connection) -> None:
    """Drop the unique index (best-effort rollback)."""
    try:
        emb_conn = _get_embeddings_conn()
    except Exception:
        return

    try:
        emb_conn.execute("DROP INDEX IF EXISTS idx_embeddings_sighting_model_vector")
        emb_conn.commit()
    finally:
        emb_conn.close()
