"""
Versioned migration runner for SQLite databases.

Discovers migration modules in the versions/ directory, applies them
in order, and tracks applied versions in a schema_migrations table.
"""

import importlib
import logging
import pkgutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)

VERSIONS_PACKAGE = "app.migrations.versions"
VERSIONS_DIR = Path(__file__).parent / "versions"

PRAGMAS = [
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA busy_timeout = 30000",
]

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and safety pragmas."""
    for pragma in PRAGMAS:
        conn.execute(pragma)


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations tracking table if it doesn't exist."""
    conn.execute(SCHEMA_MIGRATIONS_DDL)
    conn.commit()


def _discover_migrations() -> list[ModuleType]:
    """
    Dynamically import all migration modules from the versions/ directory.
    Returns them sorted by VERSION number.
    """
    migrations: list[ModuleType] = []

    for finder, module_name, _ in pkgutil.iter_modules([str(VERSIONS_DIR)]):
        full_name = f"{VERSIONS_PACKAGE}.{module_name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception as exc:
            logger.error("Failed to import migration %s: %s", full_name, exc)
            raise

        # Validate module interface
        for attr in ("VERSION", "NAME", "up", "down"):
            if not hasattr(mod, attr):
                raise AttributeError(
                    f"Migration {full_name} missing required attribute: {attr}"
                )

        migrations.append(mod)

    migrations.sort(key=lambda m: m.VERSION)
    return migrations


def _get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of already-applied migration versions."""
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row[0] for row in cursor.fetchall()}


def get_current_version(conn: sqlite3.Connection) -> int:
    """
    Return the highest applied migration version, or 0 if none applied.
    Ensures the migrations table exists before querying.
    """
    _ensure_migrations_table(conn)
    cursor = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    )
    return cursor.fetchone()[0]


def run_migrations(conn: sqlite3.Connection) -> int:
    """
    Apply all pending migrations in order.

    Args:
        conn: An open sqlite3 connection to the target database.

    Returns:
        The final schema version after all migrations are applied.
    """
    _apply_pragmas(conn)
    _ensure_migrations_table(conn)

    applied = _get_applied_versions(conn)
    migrations = _discover_migrations()
    newly_applied = 0

    for migration in migrations:
        if migration.VERSION in applied:
            continue

        logger.info(
            "Applying migration %03d: %s", migration.VERSION, migration.NAME
        )

        try:
            # Run the migration within a transaction
            conn.execute("BEGIN")
            migration.up(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.VERSION,
                    migration.NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            newly_applied += 1
            logger.info(
                "Migration %03d applied successfully.", migration.VERSION
            )
        except Exception:
            conn.rollback()
            logger.exception(
                "Migration %03d failed, rolled back.", migration.VERSION
            )
            raise

    if newly_applied == 0:
        logger.info("Database schema is up to date.")
    else:
        logger.info("Applied %d migration(s).", newly_applied)

    return get_current_version(conn)
