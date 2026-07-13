"""
Fish matching service for FishDex AI Server.
Uses SQLite for embedding storage and cosine similarity for re-identification.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_instance: Optional["MatchingService"] = None

from app.utils.area_utils import normalize_area_code
import math

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fish_embeddings (
    id TEXT PRIMARY KEY,
    fish_id TEXT NOT NULL,
    sighting_id TEXT,
    species_slug TEXT NOT NULL,
    area_code TEXT,
    latitude REAL,
    longitude REAL,
    embedding BLOB NOT NULL,
    model_version TEXT DEFAULT 'resnet50_v2',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_species_area ON fish_embeddings(species_slug, area_code);
CREATE INDEX IF NOT EXISTS idx_species ON fish_embeddings(species_slug);
CREATE INDEX IF NOT EXISTS idx_fish_id ON fish_embeddings(fish_id);
"""


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class MatchingService:
    """Fish re-identification via embedding similarity in SQLite."""

    def __init__(self):
        self.db_path = Path(settings.embeddings_db_path)
        self._ensure_db()
        logger.info("MatchingService initialized (db=%s)", self.db_path)

    def _ensure_db(self):
        """Create database directory and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
        self._ensure_columns()

    def _ensure_columns(self):
        """Dynamically add missing columns to fish_embeddings table."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(fish_embeddings)")
            cols = {row[1] for row in cursor.fetchall()}
            if "latitude" not in cols:
                logger.info("Adding column fish_embeddings.latitude REAL")
                conn.execute("ALTER TABLE fish_embeddings ADD COLUMN latitude REAL")
            if "longitude" not in cols:
                logger.info("Adding column fish_embeddings.longitude REAL")
                conn.execute("ALTER TABLE fish_embeddings ADD COLUMN longitude REAL")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def find_match(
        self,
        embedding: np.ndarray,
        species_slug: str,
        area_code: Optional[str],
        threshold: float = 0.70,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
    ) -> tuple[Optional[str], float]:
        """
        Find the best matching fish_id for a given embedding.

        Searches all embeddings with the same species_slug and matches if:
        1. Normalised area codes match exactly, OR
        2. Sighting GPS coordinates lie within radius_km (default: 5.0) of a stored candidate.

        Returns:
            (fish_id, score) if score >= threshold, else (None, best_score).
        """
        if not species_slug:
            return (None, 0.0)

        query_area = normalize_area_code(area_code)
        radius = radius_km or settings.nearby_area_radius_km or 5.0

        with self._connect() as conn:
            # Query candidates of the same species
            rows = conn.execute(
                """
                SELECT fish_id, embedding, area_code, latitude, longitude
                FROM fish_embeddings
                WHERE species_slug = ?
                """,
                (species_slug,),
            ).fetchall()

        if not rows:
            return (None, 0.0)

        best_fish_id: Optional[str] = None
        best_score = 0.0

        # Normalize query embedding once
        embedding = embedding.flatten().astype(np.float32)

        for fish_id, emb_blob, stored_area, stored_lat, stored_lng in rows:
            stored_area_norm = normalize_area_code(stored_area)

            # Match criteria: same normalized area OR within geographic proximity radius
            same_area = bool(query_area != "XX" and stored_area_norm == query_area)

            nearby = False
            if (
                latitude is not None
                and longitude is not None
                and stored_lat is not None
                and stored_lng is not None
            ):
                try:
                    dist = _haversine_km(
                        float(latitude),
                        float(longitude),
                        float(stored_lat),
                        float(stored_lng),
                    )
                    nearby = (dist <= radius)
                except Exception:
                    nearby = False

            # If not in the same area and not geographically nearby, ignore this candidate
            if not same_area and not nearby:
                continue

            stored = np.frombuffer(emb_blob, dtype=np.float32)
            score = _cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best_fish_id = fish_id

        if best_score >= threshold and best_fish_id:
            logger.info(
                "Match found: fish_id=%s score=%.4f threshold=%.2f",
                best_fish_id,
                best_score,
                threshold,
            )
            return (best_fish_id, best_score)

        logger.info(
            "No match above threshold %.2f. Best candidate=%s score=%.4f",
            threshold,
            best_fish_id,
            best_score,
        )
        return (None, best_score)

    def store_embedding(
        self,
        fish_id: str,
        sighting_id: str,
        species_slug: str,
        area_code: Optional[str],
        embedding: np.ndarray,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ):
        """Store an embedding for a fish sighting with optional coordinates."""
        import uuid

        record_id = str(uuid.uuid4())
        emb_bytes = embedding.flatten().astype(np.float32).tobytes()
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fish_embeddings (
                    id, fish_id, sighting_id, species_slug, area_code,
                    latitude, longitude, embedding, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    fish_id,
                    sighting_id,
                    species_slug,
                    area_code,
                    latitude,
                    longitude,
                    emb_bytes,
                    now,
                ),
            )
            conn.commit()

        logger.info(
            "Stored embedding for fish_id=%s sighting=%s (lat=%s, lon=%s)",
            fish_id, sighting_id, latitude, longitude
        )

    def get_fish_embeddings(self, fish_id: str) -> list[np.ndarray]:
        """Retrieve all stored embeddings for a given fish_id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT embedding FROM fish_embeddings WHERE fish_id = ?",
                (fish_id,),
            ).fetchall()

        return [
            np.frombuffer(row[0], dtype=np.float32) for row in rows
        ]

    def count_fish_in_area(self, area_code: str, species_slug: str) -> int:
        """Count distinct fish of a species in an area."""
        norm_area = normalize_area_code(area_code)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT fish_id) FROM fish_embeddings
                WHERE area_code = ? AND species_slug = ?
                """,
                (norm_area, species_slug),
            ).fetchone()

        return row[0] if row else 0


def get_matching_service() -> MatchingService:
    """Return the singleton MatchingService instance."""
    global _instance
    if _instance is None:
        _instance = MatchingService()
    return _instance
