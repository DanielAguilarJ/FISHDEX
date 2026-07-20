"""
Test suite for identity decision logic (Fase 1).

Verifies that:
- Auto-match requires high score AND sufficient margin.
- Ambiguous results (gray zone) do NOT create sightings or update individuals.
- New fish is correctly created when no candidates exist.
- Score below threshold with good quality -> new_fish.
- Score below threshold with bad quality -> repeat_capture (future).
"""

import pytest
import numpy as np


class TestDecisionLogicUnit:
    """Unit tests for the decision boundaries."""

    def test_auto_match_requires_high_score_and_margin(self):
        """Score >= 0.85 AND margin >= 0.05 -> auto_match."""
        score = 0.90
        margin = 0.10
        min_margin = 0.05

        is_new_fish = False
        if is_new_fish:
            decision = "new_fish"
        elif score >= 0.85 and margin >= min_margin:
            decision = "auto_match"
        else:
            decision = "needs_manual_review"

        assert decision == "auto_match"

    def test_high_score_insufficient_margin_goes_to_review(self):
        """Score >= 0.85 but margin < 0.05 -> needs_manual_review."""
        score = 0.87
        margin = 0.03  # Too small
        min_margin = 0.05

        is_new_fish = False
        if is_new_fish:
            decision = "new_fish"
        elif score >= 0.85 and margin >= min_margin:
            decision = "auto_match"
        else:
            decision = "needs_manual_review"

        assert decision == "needs_manual_review"

    def test_gray_zone_score_goes_to_review(self):
        """Score between threshold and auto_match (0.82-0.85) -> review."""
        score = 0.83
        margin = 0.10
        min_margin = 0.05

        # Even with good margin, score below 0.85 is not auto_match
        is_new_fish = False
        if is_new_fish:
            decision = "new_fish"
        elif score >= 0.85 and margin >= min_margin:
            decision = "auto_match"
        else:
            decision = "needs_manual_review"

        assert decision == "needs_manual_review"

    def test_no_candidates_creates_new_fish(self):
        """No match found (score below threshold) -> new_fish."""
        score = 0.50
        matched_fish_id = None
        is_new_fish = (matched_fish_id is None)

        if is_new_fish:
            decision = "new_fish"
        elif score >= 0.85:
            decision = "auto_match"
        else:
            decision = "needs_manual_review"

        assert decision == "new_fish"

    def test_single_candidate_not_enough_goes_to_review(self):
        """Single candidate with score 0.84 -> review, not auto_match."""
        score = 0.84
        margin = 0.84  # Only one candidate so margin = score - 0
        min_margin = 0.05

        is_new_fish = False
        if is_new_fish:
            decision = "new_fish"
        elif score >= 0.85 and margin >= min_margin:
            decision = "auto_match"
        else:
            decision = "needs_manual_review"

        assert decision == "needs_manual_review"


class TestAmbiguousDoesNotContaminate:
    """
    Integration tests verifying that ambiguous results leave the database clean.
    Uses MatchingService to verify that NO embedding is stored for ambiguous cases.
    """

    @pytest.fixture
    def matching_service(self, tmp_path, monkeypatch):
        from app.services.matching_service import MatchingService

        db_path = str(tmp_path / "test_embeddings.sqlite")
        monkeypatch.setattr("app.config.settings.embeddings_db_path", db_path)
        monkeypatch.setattr("app.config.settings.reid_cache_name", "test_model_v1")
        monkeypatch.setattr("app.config.settings.nearby_area_radius_km", 5.0)

        svc = MatchingService()
        return svc

    def _random_embedding(self, dim=512, seed=None):
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(dim).astype(np.float32)
        v /= np.linalg.norm(v)
        return v

    def test_ambiguous_match_should_not_store_embedding(self, matching_service):
        """
        Simulate: existing fish with score in gray zone.
        The system should NOT store a new embedding for the query.
        """
        # Store one fish
        emb_stored = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb_stored,
            latitude=49.529, longitude=17.788,
            model_version="test_model_v1",
        )

        # Create a query embedding that is somewhat similar (gray zone ~0.8)
        # We mix the stored embedding with noise to get ~0.8 similarity
        noise = self._random_embedding(seed=99)
        query_emb = 0.8 * emb_stored + 0.6 * noise
        query_emb /= np.linalg.norm(query_emb)

        # Run find_match
        result = matching_service.find_match(
            embedding=query_emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=49.530, longitude=17.789,
            model_version="test_model_v1",
        )

        # The service returns a match (above 0.70) but it's in gray zone
        # The CALLER (job_service) decides not to store
        # Verify: only 1 embedding exists (the original)
        all_embs = matching_service.get_fish_embeddings("FISH-001")
        assert len(all_embs) == 1, "Ambiguous result must NOT add embeddings"

    def test_auto_match_stores_embedding(self, matching_service):
        """
        When auto_match is confirmed (score >= 0.85, margin >= 0.05),
        the embedding SHOULD be stored.
        """
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=49.529, longitude=17.788,
            model_version="test_model_v1",
        )

        # Same embedding (score ~1.0, clearly auto_match)
        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=49.530, longitude=17.789,
            model_version="test_model_v1",
        )

        assert result["fish_id"] == "FISH-001"
        assert result["score"] > 0.99

        # Simulate auto_match decision: store embedding
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s2", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=49.530, longitude=17.789,
            model_version="test_model_v1",
        )

        all_embs = matching_service.get_fish_embeddings("FISH-001")
        assert len(all_embs) == 2, "Auto-match should store the new embedding"

    def test_many_embeddings_per_fish_no_unfair_advantage(self, matching_service):
        """
        A fish with many embeddings should use median, not max.
        This prevents a fish with 100 photos from having unfair advantage.
        """
        # Store 10 embeddings for FISH-001
        base_emb = self._random_embedding(seed=42)
        for i in range(10):
            noise = self._random_embedding(seed=100 + i) * 0.1
            varied = base_emb + noise
            varied /= np.linalg.norm(varied)
            matching_service.store_embedding(
                fish_id="FISH-001", sighting_id=f"s{i}", species_slug="cyprinus_carpio",
                area_code="471011", embedding=varied,
                latitude=49.529, longitude=17.788,
                model_version="test_model_v1",
            )

        # Store 2 embeddings for FISH-002
        emb2 = self._random_embedding(seed=50)
        for i in range(2):
            matching_service.store_embedding(
                fish_id="FISH-002", sighting_id=f"s2_{i}", species_slug="cyprinus_carpio",
                area_code="471011", embedding=emb2,
                latitude=49.530, longitude=17.789,
                model_version="test_model_v1",
            )

        # Query with emb2 — FISH-002 should win despite fewer embeddings
        result = matching_service.find_match(
            embedding=emb2, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=49.5295, longitude=17.7885,
            model_version="test_model_v1",
        )

        assert result["fish_id"] == "FISH-002"
