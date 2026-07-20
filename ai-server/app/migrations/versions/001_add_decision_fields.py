"""
Migration 001: Add decision and metadata fields to identification_jobs.

Extends the identification_jobs table with columns for decision logic,
scoring metrics, GPS data, area matching, and review tracking.
"""

import sqlite3

VERSION = 1
NAME = "add_decision_fields"

COLUMNS = [
    ("decision", "TEXT"),
    ("proposed_fish_id", "TEXT"),
    ("top1_score", "REAL"),
    ("top2_score", "REAL"),
    ("match_margin", "REAL"),
    ("agreement_ratio", "REAL"),
    ("winning_votes", "INTEGER"),
    ("total_query_frames", "INTEGER"),
    ("minimum_distance_m", "REAL"),
    ("matched_area_code", "TEXT"),
    ("cross_area", "INTEGER DEFAULT 0"),
    ("model_version", "TEXT"),
    ("index_version", "TEXT"),
    ("quality_score", "REAL"),
    ("quality_json", "TEXT"),
    ("decision_reasons_json", "TEXT"),
    ("gps_accuracy_m", "REAL"),
    ("gps_timestamp", "TEXT"),
    ("gps_is_mocked", "INTEGER DEFAULT 0"),
    ("gps_source", "TEXT"),
    ("area_selection_source", "TEXT"),
    ("area_catalog_version", "TEXT"),
    ("area_consistency_status", "TEXT"),
    ("review_case_id", "TEXT"),
    ("result_json", "TEXT"),
    ("updated_at", "TEXT"),
]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    return column in existing


def up(conn: sqlite3.Connection) -> None:
    """Add decision and metadata columns to identification_jobs."""
    for col_name, col_type in COLUMNS:
        if not _column_exists(conn, "identification_jobs", col_name):
            conn.execute(
                f"ALTER TABLE identification_jobs ADD COLUMN {col_name} {col_type}"
            )


def down(conn: sqlite3.Connection) -> None:
    """
    Best-effort rollback: SQLite does not support DROP COLUMN before 3.35.0.
    On older versions this is a no-op; on 3.35+ we attempt removal.
    """
    version = sqlite3.sqlite_version_info
    if version < (3, 35, 0):
        return

    for col_name, _ in reversed(COLUMNS):
        if _column_exists(conn, "identification_jobs", col_name):
            try:
                conn.execute(
                    f"ALTER TABLE identification_jobs DROP COLUMN {col_name}"
                )
            except sqlite3.OperationalError:
                # Column may have been added by _ensure_columns before migration
                pass
