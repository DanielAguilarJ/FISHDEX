"""
Migration 002: Create identification_review_cases table.

Stores cases flagged for human review with decision context and resolution tracking.
"""

import sqlite3

VERSION = 2
NAME = "create_review_cases"


def up(conn: sqlite3.Connection) -> None:
    """Create the review cases table and indexes."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS identification_review_cases (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            proposed_fish_id TEXT,
            proposed_decision TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            reason_codes_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            resolution TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_cases_state
        ON identification_review_cases(state)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_review_cases_job
        ON identification_review_cases(job_id)
    """)


def down(conn: sqlite3.Connection) -> None:
    """Drop the review cases table and indexes."""
    conn.execute("DROP INDEX IF EXISTS idx_review_cases_job")
    conn.execute("DROP INDEX IF EXISTS idx_review_cases_state")
    conn.execute("DROP TABLE IF EXISTS identification_review_cases")
