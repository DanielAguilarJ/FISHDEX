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

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fish_embeddings (
    id TEXT PRIMARY KEY,
    fish_id TEXT NOT NULL,
    sighting_id TEXT,
    species_slug TEXT NOT NULL,
    area_code TEXT,
    embedding BLOB NOT NULL,
    model_version TEXT DEFAULT 'resnet50_v2',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_species_area ON fish_embeddings(species_slug, area_code);
"""


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


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

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection."""
        return sqlite3.connect(str(self.db_path))

    def find_match(
        self,
        embedding: np.ndarray,
        species_slug: str,
        area_code: str,
        threshold: float = 0.70,
    ) -> tuple[Optional[str], float]:
        """
        Find the best matching fish_id for a given embedding.

        Searches all embeddings with the same species_slug and area_code
        (plus nearby area codes sharing the same prefix up to last separator).

        Returns:
            (fish_id, score) if score >= threshold, else (None, best_score).
        """
        # Build area filter: exact area + parent area prefix
        area_patterns = [area_code]
        if area_code and "_" in area_code:
            # e.g. "uk_thames_upper" -> also match "uk_thames_%"
            parent = "_".join(area_code.split("_")[:-1])
            area_patterns.append(f"{parent}_%")

        with self._connect() as conn:
            # Query candidates
            placeholders = " OR ".join(
                ["area_code = ?"] + ["area_code LIKE ?" for _ in area_patterns[1:]]
            )
            query = f"""
                SELECT fish_id, embedding FROM fish_embeddings
                WHERE species_slug = ? AND ({placeholders})
            """
            params = [species_slug] + area_patterns
            rows = conn.execute(query, params).fetchall()

        if not rows:
            return (None, 0.0)

        best_fish_id: Optional[str] = None
        best_score = 0.0

        # Normalize query embedding once
        embedding = embedding.flatten().astype(np.float32)

        for fish_id, emb_blob in rows:
            stored = np.frombuffer(emb_blob, dtype=np.float32)
            score = _cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best_fish_id = fish_id

        if best_score >= threshold:
            logger.debug(
                "Match found: fish_id=%s score=%.4f", best_fish_id, best_score
            )
            return (best_fish_id, best_score)

        return (None, best_score)

    def store_embedding(
        self,
        fish_id: str,
        sighting_id: str,
        species_slug: str,
        area_code: str,
        embedding: np.ndarray,
    ):
        """Store an embedding for a fish sighting."""
        import uuid

        record_id = str(uuid.uuid4())
        emb_bytes = embedding.flatten().astype(np.float32).tobytes()
        now = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fish_embeddings (id, fish_id, sighting_id, species_slug, area_code, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, fish_id, sighting_id, species_slug, area_code, emb_bytes, now),
            )
            conn.commit()

        logger.debug(
            "Stored embedding for fish_id=%s sighting=%s", fish_id, sighting_id
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
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT fish_id) FROM fish_embeddings
                WHERE area_code = ? AND species_slug = ?
                """,
                (area_code, species_slug),
            ).fetchone()

        return row[0] if row else 0


def get_matching_service() -> MatchingService:
    """Return the singleton MatchingService instance."""
    global _instance
    if _instance is None:
        _instance = MatchingService()
    return _instance
