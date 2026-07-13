import sqlite3
import os
import logging
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(settings.server_data_dir) / "fishdex_local.sqlite"

def get_db_connection() -> sqlite3.Connection:
    """Get a connection to the local SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_columns(cursor, table_name: str, required_columns: dict[str, str]) -> None:
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            logger.info("Adding missing column %s.%s %s", table_name, column_name, column_type)
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )

def init_db():
    """Create database tables if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'fisherman',
            created_at TEXT NOT NULL
        )
    """)
    
    # 2. Identification Jobs Table
    cursor.execute("""
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
    """)
    
    _identification_job_columns = {
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
        # NUEVO
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
    }
    _ensure_columns(cursor, "identification_jobs", _identification_job_columns)
    
    # 3. Fish Sightings Table
    cursor.execute("""
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
    """)

    _fish_sightings_columns = {
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
        "detection_confidence": "REAL",
        "classification_confidence": "REAL",
        "match_confidence": "REAL",
        "catch_number": "INTEGER",
        # NUEVO
        "media_type": "TEXT DEFAULT 'video'",
        "video_filename": "TEXT",
        "rarity": "TEXT",
        "previous_sighting_id": "TEXT",
        "total_sightings_before": "INTEGER DEFAULT 0",
        "total_sightings_after": "INTEGER DEFAULT 1",
        "linkage_json": "TEXT",
    }
    _ensure_columns(cursor, "fish_sightings", _fish_sightings_columns)
    
    # 4. Fish Individuals Table
    cursor.execute("""
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
    """)

    _fish_individuals_columns = {
        "area_name": "TEXT",
        "latest_sighting_id": "TEXT",
        "latest_document_filename": "TEXT",
        # NUEVO
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
    _ensure_columns(cursor, "fish_individuals", _fish_individuals_columns)
    
    # 5. User Stats Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            total_xp INTEGER DEFAULT 0,
            total_sightings INTEGER DEFAULT 0,
            total_species INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)

    # 6. Uniqueness & Performance Indexes
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fish_sightings_job_id_unique
        ON fish_sightings(job_id)
        WHERE job_id IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fish_sightings_fish_catch_unique
        ON fish_sightings(fish_id, catch_number)
        WHERE fish_id IS NOT NULL AND catch_number IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fish_sightings_fish_id ON fish_sightings(fish_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_fish_sightings_user_id ON fish_sightings(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_identification_jobs_status ON identification_jobs(status)
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Local SQLite database initialized at {DB_PATH.resolve()}")
