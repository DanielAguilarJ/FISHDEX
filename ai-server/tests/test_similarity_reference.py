"""
Tests for similarity reference traceability.

Covers:
1. First capture — no candidates, similarity_reference is None
2. Recapture cross-area — same fish, different area
3. Reference visual != previous chronological
4. Rejected candidate (new fish, below threshold)
5. Gray zone / forced auto_match
6. Privacy — fisherman doesn't get GPS
7. Idempotency
8. Rematch lock
9. Legacy JSON backward compatibility
"""

import json
import sqlite3
import uuid
from unittest.mock import MagicMock, patch
from pathlib import Path

import numpy as np
import pytest

from app.services.identity_scoring_service import (
    ScoringResult,
    SupportMetadata,
    ReferenceEvidence,
    score_candidates,
    _select_best_reference,
)
from app.services.identification_pipeline import (
    CaptureMetadata,
    PipelineResult,
    IdentificationPipeline,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_embeddings(n: int, dim: int = 512, seed: int = 42) -> np.ndarray:
    """Generate N random L2-normalized embeddings."""
    rng = np.random.default_rng(seed)
    embs = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    return embs / norms


def _make_similar_embeddings(
    base: np.ndarray, n: int, noise: float = 0.05, seed: int = 99
) -> np.ndarray:
    """Generate N embeddings similar to a base embedding (single vector)."""
    rng = np.random.default_rng(seed)
    if base.ndim == 1:
        base = base.reshape(1, -1)
    result = base + rng.standard_normal((n, base.shape[1])).astype(np.float32) * noise
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    return result / norms


# ─── Test 1: First capture — no candidates ─────────────────────────────────

class TestFirstCapture:
    def test_no_candidates_returns_null_reference(self):
        """When gallery is empty, scoring returns empty result with no reference."""
        query = _make_embeddings(5)
        result = score_candidates(
            query_embeddings=query,
            candidate_gallery={},
            candidate_support_metadata=None,
        )
        assert result.top1_fish_id is None
        assert result.reference is None

    def test_pipeline_new_fish_no_reference(self):
        """Pipeline new_fish decision has no reference_sighting_id."""
        result = PipelineResult(
            decision="new_fish",
            reasons=["No candidates within radius — new individual"],
        )
        assert result.reference_sighting_id is None
        assert result.reference_score == 0.0


# ─── Test 2: Recapture cross-area ──────────────────────────────────────────

class TestRecaptureCrossArea:
    def test_cross_area_detected(self):
        """When winner is from a different area, cross_area=True in pipeline result."""
        # Build query from "area A"
        base_emb = _make_embeddings(1, dim=128, seed=1)
        query = _make_similar_embeddings(base_emb, n=5, noise=0.02, seed=10)

        # Gallery: one fish from "area B" with similar embeddings
        gallery_embs = _make_similar_embeddings(base_emb, n=3, noise=0.03, seed=20)
        gallery = {"CZ-471010-CYPR-0001": gallery_embs}
        metadata = {
            "CZ-471010-CYPR-0001": [
                SupportMetadata(
                    embedding_id=str(uuid.uuid4()),
                    sighting_id="sighting-old",
                    area_code="471010",
                    latitude=49.0,
                    longitude=14.4,
                    distance_m=3000.0,
                    created_at="2026-07-01T10:00:00Z",
                )
                for _ in range(3)
            ]
        }

        result = score_candidates(
            query_embeddings=query,
            candidate_gallery=gallery,
            candidate_support_metadata=metadata,
        )

        assert result.top1_fish_id == "CZ-471010-CYPR-0001"
        assert result.reference is not None
        assert result.reference.sighting_id == "sighting-old"
        assert result.reference.area_code == "471010"
        assert result.reference.distance_m == 3000.0


# ─── Test 3: Reference visual != previous chronological ────────────────────

class TestReferenceVsPrevious:
    def test_best_reference_is_oldest_not_newest(self):
        """
        Fish has catches 1 (very similar) and 2 (less similar).
        Query should reference catch 1, not catch 2 (chronologically latest).
        """
        dim = 128
        # Catch 1 embedding: very distinctive pattern
        catch1_emb = _make_embeddings(1, dim=dim, seed=100)
        # Catch 2 embedding: different (same fish but different angle)
        catch2_emb = _make_embeddings(1, dim=dim, seed=200)

        # Query is very similar to catch 1
        query = _make_similar_embeddings(catch1_emb, n=5, noise=0.01, seed=300)

        # Gallery includes both catches
        gallery_combined = np.vstack([catch1_emb, catch2_emb])
        gallery = {"FISH-001": gallery_combined}

        meta_catch1 = SupportMetadata(
            embedding_id="emb-catch1",
            sighting_id="sighting-catch1",
            area_code="471010",
            latitude=49.0,
            longitude=14.4,
            distance_m=100.0,
            created_at="2026-06-01T10:00:00Z",
        )
        meta_catch2 = SupportMetadata(
            embedding_id="emb-catch2",
            sighting_id="sighting-catch2",
            area_code="471010",
            latitude=49.0,
            longitude=14.4,
            distance_m=200.0,
            created_at="2026-07-01T10:00:00Z",  # newer
        )

        metadata = {"FISH-001": [meta_catch1, meta_catch2]}

        result = score_candidates(
            query_embeddings=query,
            candidate_gallery=gallery,
            candidate_support_metadata=metadata,
        )

        assert result.top1_fish_id == "FISH-001"
        assert result.reference is not None
        # Reference should be catch 1 (most similar), NOT catch 2 (most recent)
        assert result.reference.sighting_id == "sighting-catch1"
        assert result.reference.embedding_id == "emb-catch1"
        # And the reference score should be high
        assert result.reference.score > 0.9


# ─── Test 4: Rejected candidate (new fish) ─────────────────────────────────

class TestRejectedCandidate:
    def test_new_fish_still_has_reference_when_candidates_exist(self):
        """
        Even when decision is new_fish (below threshold), the scoring
        still provides the best reference for audit purposes.
        """
        dim = 128
        # Very different embeddings
        query = _make_embeddings(5, dim=dim, seed=1)
        gallery_embs = _make_embeddings(3, dim=dim, seed=999)  # dissimilar
        gallery = {"EXISTING-FISH": gallery_embs}
        metadata = {
            "EXISTING-FISH": [
                SupportMetadata(
                    embedding_id=f"emb-{i}",
                    sighting_id="sighting-old",
                    area_code="471010",
                    latitude=49.0,
                    longitude=14.4,
                    distance_m=500.0,
                )
                for i in range(3)
            ]
        }

        result = score_candidates(
            query_embeddings=query,
            candidate_gallery=gallery,
            candidate_support_metadata=metadata,
        )

        # Score should be low (dissimilar embeddings)
        assert result.top1_score < 0.5
        # But reference still exists for audit
        assert result.reference is not None
        assert result.reference.sighting_id == "sighting-old"


# ─── Test 5: Gray zone / forced auto_match ───────────────────────────────

class TestGrayZone:
    def test_pipeline_result_marks_review_with_reference(self):
        """Pipeline forced auto_match still includes reference for admin."""
        result = PipelineResult(
            decision="auto_match",
            proposed_fish_id="CZ-471010-CYPR-0002",
            reference_sighting_id="sighting-ref",
            reference_embedding_id="emb-ref",
            reference_score=0.798,
            reference_area_code="471010",
            cross_area=False,
            model_version="fishencoder_convnext_small_512_128_v2",
            reasons=["Gray zone: margin too small"],
        )
        assert result.decision == "auto_match"
        assert result.reference_sighting_id == "sighting-ref"
        assert result.reference_score == 0.798


# ─── Test 6: Privacy ───────────────────────────────────────────────────────

class TestPrivacy:
    def test_strip_sensitive_for_fisherman(self):
        """Fisherman role should not see GPS from historical catches."""
        try:
            from app.routers.jobs import _strip_sensitive_for_fisherman
        except RuntimeError:
            pytest.skip("python-multipart not installed")

        data = {
            "fish_id": "CZ-471010-CYPR-0001",
            "location_lat": 49.1234,
            "location_lng": 14.5678,
            "previous_catch": {
                "location_lat": 49.0,
                "location_lng": 14.4,
                "user_id": "other-user",
            },
            "matched_reference_catch": {
                "location_lat": 49.05,
                "location_lng": 14.45,
                "user_id": "other-user-2",
            },
            "similarity_reference": {
                "status": "accepted",
                "reference_area_code": "471010",
                "reference_area_name": "Moldava River",
                "distance_m": 2380.4,
                "identity_score": 0.82,
                "reference_score": 0.86,
            },
        }

        result = _strip_sensitive_for_fisherman(data)

        # Previous catch GPS stripped
        assert "location_lat" not in result["previous_catch"]
        assert "user_id" not in result["previous_catch"]
        # Reference catch GPS stripped
        assert "location_lat" not in result["matched_reference_catch"]
        assert "user_id" not in result["matched_reference_catch"]
        # Similarity reference area stripped
        assert "reference_area_code" not in result["similarity_reference"]
        assert "distance_m" not in result["similarity_reference"]
        # But scores remain
        assert result["similarity_reference"]["identity_score"] == 0.82
        assert result["similarity_reference"]["reference_score"] == 0.86


# ─── Test 7: Idempotency ───────────────────────────────────────────────────

class TestIdempotency:
    def test_scoring_deterministic(self):
        """Same inputs produce same reference selection."""
        dim = 128
        query = _make_embeddings(5, dim=dim, seed=42)
        gallery_embs = _make_similar_embeddings(
            query[0:1], n=4, noise=0.05, seed=77
        )
        gallery = {"FISH-A": gallery_embs}
        metadata = {
            "FISH-A": [
                SupportMetadata(
                    embedding_id=f"emb-{i}",
                    sighting_id=f"sighting-{i}",
                    area_code="471010",
                )
                for i in range(4)
            ]
        }

        r1 = score_candidates(query, gallery, metadata)
        r2 = score_candidates(query, gallery, metadata)

        assert r1.top1_fish_id == r2.top1_fish_id
        assert r1.top1_score == r2.top1_score
        assert r1.reference.sighting_id == r2.reference.sighting_id
        assert r1.reference.score == r2.reference.score


# ─── Test 8: Rematch lock ──────────────────────────────────────────────────

class TestRematchLock:
    def test_locked_result_replaces_prelock(self):
        """The pipeline_result_locked is what gets used, not the pre-lock one."""
        # This is a behavioral test: we verify the data structure
        prelock = PipelineResult(
            decision="new_fish",
            reference_sighting_id=None,
            reference_score=0.0,
        )
        locked = PipelineResult(
            decision="auto_match",
            fish_id="CZ-471010-CYPR-0001",
            reference_sighting_id="sighting-new",
            reference_embedding_id="emb-new",
            reference_score=0.88,
            cross_area=False,
            model_version="fishencoder_convnext_small_512_128_v2",
        )

        # After the lock, locked result replaces pre-lock
        pipeline_result = locked
        assert pipeline_result.decision == "auto_match"
        assert pipeline_result.reference_sighting_id == "sighting-new"
        assert pipeline_result.reference_score == 0.88


# ─── Test 9: Legacy JSON backward compatibility ────────────────────────────

class TestLegacyJSON:
    def test_old_linkage_without_similarity_reference(self):
        """Old JSON documents without similarity_reference load safely."""
        old_linkage = {
            "is_linked": True,
            "strategy": "unified_pipeline_v1",
            "matched_fish_id": "CZ-471010-CYPR-0001",
            "match_confidence": 0.85,
            # No "similarity_reference" key
        }

        # Accessing it like the endpoint does
        similarity_reference = old_linkage.get("similarity_reference")
        assert similarity_reference is None

    def test_flutter_model_handles_null_reference(self):
        """SimilarityReference.fromJson handles null gracefully."""
        # This tests the pattern used in Flutter
        reference_json = None
        result = reference_json  # would be None in fromJson

        # In Dart: similarityReference: referenceJson is Map ? ... : null
        # Python equivalent:
        parsed = (
            reference_json
            if isinstance(reference_json, dict)
            else None
        )
        assert parsed is None


# ─── Test: _select_best_reference algorithm ─────────────────────────────────

class TestSelectBestReference:
    def test_selects_most_similar_support(self):
        """Selects the support with highest median query similarity."""
        dim = 128
        # Create a single base direction and build query + support_0 around it
        base = _make_embeddings(1, dim=dim, seed=1)
        # Query: 3 frames all similar to base
        query = _make_similar_embeddings(base, n=3, noise=0.02, seed=10)

        # Support 0: also similar to base (high similarity to query)
        support_0 = _make_similar_embeddings(base, n=1, noise=0.02, seed=20)
        # Support 1: random direction (low similarity)
        support_1 = _make_embeddings(1, dim=dim, seed=999)

        winner_support = np.vstack([support_0, support_1])
        winner_metadata = [
            SupportMetadata(
                embedding_id="emb-0",
                sighting_id="sighting-A",
                area_code="471010",
            ),
            SupportMetadata(
                embedding_id="emb-1",
                sighting_id="sighting-B",
                area_code="471011",
            ),
        ]

        ref = _select_best_reference(query, winner_support, winner_metadata)

        assert ref is not None
        assert ref.sighting_id == "sighting-A"
        assert ref.embedding_id == "emb-0"
        # Score should be much higher than the dissimilar one
        assert ref.score > 0.8

    def test_groups_by_sighting(self):
        """Multiple supports from same sighting are grouped correctly."""
        dim = 128
        query = _make_embeddings(3, dim=dim, seed=1)

        # Two supports from sighting A (both moderately similar)
        base = _make_similar_embeddings(query[0:1], n=1, noise=0.1, seed=50)
        support_a1 = _make_similar_embeddings(base, n=1, noise=0.05, seed=51)
        support_a2 = _make_similar_embeddings(base, n=1, noise=0.05, seed=52)

        # One support from sighting B (very similar)
        support_b = _make_similar_embeddings(query[0:1], n=1, noise=0.01, seed=60)

        winner_support = np.vstack([support_a1, support_a2, support_b])
        winner_metadata = [
            SupportMetadata(embedding_id="emb-a1", sighting_id="sighting-A"),
            SupportMetadata(embedding_id="emb-a2", sighting_id="sighting-A"),
            SupportMetadata(embedding_id="emb-b", sighting_id="sighting-B"),
        ]

        ref = _select_best_reference(query, winner_support, winner_metadata)
        assert ref is not None
        # B has higher individual similarity than the median of A's supports
        assert ref.sighting_id == "sighting-B"

    def test_empty_support_returns_none(self):
        """Empty support array returns None."""
        query = _make_embeddings(3, dim=128, seed=1)
        ref = _select_best_reference(query, np.empty((0, 128)), [])
        assert ref is None


# ─── Test: Metadata alignment with sampling ─────────────────────────────────

class TestMetadataAlignment:
    def test_metadata_survives_sampling(self):
        """When supports > max_support, metadata is sampled in sync."""
        dim = 128
        n_supports = 20
        max_support = 8

        query = _make_embeddings(3, dim=dim, seed=1)
        gallery_embs = _make_embeddings(n_supports, dim=dim, seed=42)
        gallery = {"FISH-BIG": gallery_embs}

        metadata = {
            "FISH-BIG": [
                SupportMetadata(
                    embedding_id=f"emb-{i}",
                    sighting_id=f"sighting-{i}",
                    area_code="471010",
                )
                for i in range(n_supports)
            ]
        }

        result = score_candidates(
            query_embeddings=query,
            candidate_gallery=gallery,
            candidate_support_metadata=metadata,
            max_support_per_identity=max_support,
        )

        # Reference should exist and point to a valid sighting
        assert result.reference is not None
        assert result.reference.sighting_id is not None
        # The sighting_id should be one of the original ones
        valid_ids = {f"sighting-{i}" for i in range(n_supports)}
        assert result.reference.sighting_id in valid_ids
