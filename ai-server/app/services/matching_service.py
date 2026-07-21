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
from app.utils.geo import is_within_radius
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
    created_at TEXT NOT NULL,
    dimensions INTEGER,
    quality_score REAL,
    frame_index INTEGER,
    vector_type TEXT DEFAULT 'prototype',
    gps_accuracy_m REAL
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
            if "dimensions" not in cols:
                logger.info("Adding column fish_embeddings.dimensions INTEGER")
                conn.execute("ALTER TABLE fish_embeddings ADD COLUMN dimensions INTEGER")
            if "vector_type" not in cols:
                logger.info("Adding column fish_embeddings.vector_type TEXT DEFAULT 'prototype'")
                conn.execute("ALTER TABLE fish_embeddings ADD COLUMN vector_type TEXT DEFAULT 'prototype'")
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
        model_version: Optional[str] = None,
    ) -> dict:
        """
        Find the best matching fish_id for a given embedding.

        STRICT RULES (Fase 1):
        - Only same species_slug candidates are considered.
        - Only embeddings with compatible model_version are compared.
        - Eligibility requires GPS distance <= radius (default 5 km)
          between the REAL GPS of the query and the REAL GPS of the historical sighting.
        - same_area NEVER bypasses the radius check.
        - If query GPS is missing, no auto-match is possible.

        Returns a dict with:
            fish_id: matched fish or None
            score: best cosine similarity
            top2_fish_id: second best candidate
            top2_score: second best score
            margin: top1 - top2
            candidates_evaluated: number of eligible candidates
            decision_context: metadata for decision engine
        """
        empty_result = {
            "fish_id": None,
            "score": 0.0,
            "top2_fish_id": None,
            "top2_score": 0.0,
            "margin": 0.0,
            "candidates_evaluated": 0,
            "decision_context": {},
        }

        if not species_slug:
            return empty_result

        # GPS is MANDATORY for matching — no GPS means no match possible
        if latitude is None or longitude is None:
            logger.warning(
                "find_match called without query GPS — no candidates eligible"
            )
            empty_result["decision_context"] = {"reason": "missing_query_gps"}
            return empty_result

        radius_m = (radius_km or settings.nearby_area_radius_km or 5.0) * 1000.0
        query_area = normalize_area_code(area_code)
        active_model = model_version or settings.reid_cache_name or "fishencoder_512_v1"

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fish_id, embedding, area_code, latitude, longitude
                FROM fish_embeddings
                WHERE species_slug = ? AND model_version = ?
                """,
                (species_slug, active_model),
            ).fetchall()

        if not rows:
            return empty_result

        # Normalize query embedding once
        embedding = embedding.flatten().astype(np.float32)

        # Collect scores per fish_id (individual-level matching)
        fish_scores: dict[str, list[float]] = {}
        fish_distances: dict[str, float] = {}
        fish_areas: dict[str, str] = {}
        candidates_evaluated = 0

        for fish_id, emb_blob, stored_area, stored_lat, stored_lng in rows:
            # STRICT: GPS distance check between real coordinates
            within, distance_m = is_within_radius(
                latitude, longitude,
                stored_lat, stored_lng,
                radius_m=radius_m,
            )

            if not within:
                continue

            candidates_evaluated += 1

            stored = np.frombuffer(emb_blob, dtype=np.float32)
            score = _cosine_similarity(embedding, stored)

            if fish_id not in fish_scores:
                fish_scores[fish_id] = []
                fish_distances[fish_id] = distance_m if distance_m is not None else 0.0
                fish_areas[fish_id] = normalize_area_code(stored_area)
            fish_scores[fish_id].append(score)

            # Track minimum distance for this individual
            if distance_m is not None and distance_m < fish_distances.get(fish_id, float("inf")):
                fish_distances[fish_id] = distance_m

        if not fish_scores:
            empty_result["decision_context"] = {"reason": "no_candidates_within_radius"}
            return empty_result

        # Aggregate per-individual: use median score across embeddings
        fish_aggregated: dict[str, float] = {}
        for fid, scores in fish_scores.items():
            # Use median for robustness against outlier embeddings
            fish_aggregated[fid] = float(np.median(scores))

        # Sort by score descending
        sorted_candidates = sorted(fish_aggregated.items(), key=lambda x: x[1], reverse=True)

        top1_fish_id, top1_score = sorted_candidates[0]
        top2_fish_id: Optional[str] = None
        top2_score = 0.0
        if len(sorted_candidates) > 1:
            top2_fish_id, top2_score = sorted_candidates[1]

        margin = top1_score - top2_score

        # Determine cross_area status
        top1_area = fish_areas.get(top1_fish_id, "XX")
        cross_area = (top1_area != query_area) and (query_area != "XX") and (top1_area != "XX")

        result = {
            "fish_id": top1_fish_id if top1_score >= threshold else None,
            "score": round(top1_score, 6),
            "top2_fish_id": top2_fish_id,
            "top2_score": round(top2_score, 6),
            "margin": round(margin, 6),
            "candidates_evaluated": candidates_evaluated,
            "decision_context": {
                "threshold_used": threshold,
                "radius_m": radius_m,
                "query_area": query_area,
                "matched_area": top1_area,
                "cross_area": cross_area,
                "minimum_distance_m": round(fish_distances.get(top1_fish_id, 0.0), 1),
                "total_individuals": len(fish_scores),
            },
        }

        if top1_score >= threshold and top1_fish_id:
            logger.info(
                "Match found: fish_id=%s score=%.4f margin=%.4f threshold=%.2f cross_area=%s",
                top1_fish_id, top1_score, margin, threshold, cross_area,
            )
        else:
            logger.info(
                "No match above threshold %.2f. Best=%s score=%.4f",
                threshold, top1_fish_id, top1_score,
            )

        return result

    def store_embedding(
        self,
        fish_id: str,
        sighting_id: str,
        species_slug: str,
        area_code: Optional[str],
        embedding: np.ndarray,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        model_version: Optional[str] = None,
        vector_type: str = "prototype",
        dimensions: int = 512,
    ):
        """Store an embedding for a fish sighting with optional coordinates.

        Validates the vector before storage:
        - Must be float32
        - Must have exactly `dimensions` elements
        - All values must be finite
        - L2 norm must be approximately 1.0

        Uses INSERT OR IGNORE with UNIQUE(sighting_id, model_version, vector_type)
        to guarantee idempotency.
        """
        import uuid

        # ── Vector validation ────────────────────────────────────────────
        vec = embedding.flatten().astype(np.float32)
        if vec.shape[0] != dimensions:
            raise ValueError(
                f"Expected embedding with {dimensions} dimensions, "
                f"got {vec.shape[0]}"
            )
        if not np.all(np.isfinite(vec)):
            raise ValueError(
                "Embedding contains non-finite values (NaN or Inf)"
            )
        norm = float(np.linalg.norm(vec))
        if not (0.95 < norm < 1.05):
            raise ValueError(
                f"Embedding not L2-normalized: norm={norm:.4f} "
                f"(expected ~1.0)"
            )

        record_id = str(uuid.uuid4())
        emb_bytes = vec.tobytes()
        now = datetime.now(timezone.utc).isoformat()
        active_model = model_version or settings.reid_cache_name or "fishencoder_512_v1"

        with self._connect() as conn:
            # INSERT OR IGNORE: if UNIQUE(sighting_id, model_version, vector_type)
            # already exists, this is a no-op (idempotent rebuild).
            conn.execute(
                """
                INSERT OR IGNORE INTO fish_embeddings (
                    id, fish_id, sighting_id, species_slug, area_code,
                    latitude, longitude, embedding, model_version, created_at,
                    dimensions, vector_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    active_model,
                    now,
                    dimensions,
                    vector_type,
                ),
            )
            conn.commit()

        logger.info(
            "Stored embedding for fish_id=%s sighting=%s model=%s (lat=%s, lon=%s)",
            fish_id, sighting_id, active_model, latitude, longitude
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

    def embedding_exists(
        self,
        sighting_id: str,
        model_version: str,
        vector_type: str = "prototype",
    ) -> bool:
        """Check if an embedding already exists for this sighting + model_version.

        Used by rebuild_embeddings to skip already-processed sightings
        (informational pre-check — the UNIQUE index is the real guard).
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM fish_embeddings "
                "WHERE sighting_id = ? AND model_version = ? "
                "AND vector_type = ? LIMIT 1",
                (sighting_id, model_version, vector_type),
            ).fetchone()
        return row is not None

    def count_active_embeddings(self, model_version: str) -> dict:
        """Count embeddings, fish, and sightings for a given model_version.

        Returns:
            {
                "embedding_count": int,
                "fish_count": int,
                "sighting_count": int,
            }
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT fish_id),
                    COUNT(DISTINCT sighting_id)
                FROM fish_embeddings
                WHERE model_version = ?
                """,
                (model_version,),
            ).fetchone()

        return {
            "embedding_count": row[0] if row else 0,
            "fish_count": row[1] if row else 0,
            "sighting_count": row[2] if row else 0,
        }


def get_matching_service() -> MatchingService:
    """Return the singleton MatchingService instance."""
    global _instance
    if _instance is None:
        _instance = MatchingService()
    return _instance
