"""
Tests for the unified IdentificationPipeline (Phase 3).

Verifies:
- Pipeline produces correct decisions for various scenarios
- Scoring integrates correctly with decision engine
- GPS radius is enforced through the pipeline
- Quality gates prevent bad captures from becoming fish
- Multi-frame voting produces expected results
"""

import pytest
import numpy as np

from app.services.identification_pipeline import (
    IdentificationPipeline,
    CaptureMetadata,
    PipelineResult,
    get_identification_pipeline,
)
from app.services.identity_scoring_service import score_candidates, ScoringResult
from app.services.identity_decision_service import (
    decide_identity,
    DecisionContext,
    IdentityDecision,
)


# Reference coordinates (BEČVA 5)
BECVA_LAT = 49.529612
BECVA_LON = 17.788836


def _make_embedding(dim=512, seed=None):
    """Create a normalized random embedding."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _make_query_embeddings(n_frames=5, seed=42, dim=512):
    """Create multiple L2-normalized query embeddings."""
    rng = np.random.default_rng(seed)
    embs = rng.standard_normal((n_frames, dim)).astype(np.float32)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    return embs / norms


class TestScoringService:
    """Unit tests for identity_scoring_service."""

    def test_perfect_match_single_candidate(self):
        """Same embedding should score ~1.0."""
        query = _make_embedding(seed=1).reshape(1, -1)
        gallery = {"FISH-A": query.copy()}

        result = score_candidates(query, gallery)
        assert result.top1_fish_id == "FISH-A"
        assert result.top1_score > 0.99
        assert result.agreement_ratio == 1.0

    def test_two_candidates_correct_winner(self):
        """Query similar to FISH-A should pick FISH-A over FISH-B."""
        base_a = _make_embedding(seed=10)
        base_b = _make_embedding(seed=20)

        # Query is very close to A
        query = (base_a * 0.95 + _make_embedding(seed=99) * 0.05)
        query /= np.linalg.norm(query)
        query = query.reshape(1, -1)

        gallery = {
            "FISH-A": base_a.reshape(1, -1),
            "FISH-B": base_b.reshape(1, -1),
        }

        result = score_candidates(query, gallery)
        assert result.top1_fish_id == "FISH-A"
        assert result.top2_fish_id == "FISH-B"
        assert result.margin > 0

    def test_multi_frame_voting(self):
        """Multiple frames should vote for the correct fish."""
        base_a = _make_embedding(seed=10)

        # 5 frames all similar to A
        rng = np.random.default_rng(42)
        query_frames = []
        for i in range(5):
            noise = rng.standard_normal(512).astype(np.float32) * 0.05
            frame = base_a + noise
            frame /= np.linalg.norm(frame)
            query_frames.append(frame)
        query = np.stack(query_frames)

        gallery = {
            "FISH-A": base_a.reshape(1, -1),
            "FISH-B": _make_embedding(seed=20).reshape(1, -1),
        }

        result = score_candidates(query, gallery)
        assert result.top1_fish_id == "FISH-A"
        assert result.winning_votes >= 4  # At least 4 of 5 frames
        assert result.agreement_ratio >= 0.8

    def test_empty_gallery_returns_zeros(self):
        """Empty gallery should return empty result."""
        query = _make_query_embeddings(n_frames=3)
        result = score_candidates(query, {})
        assert result.top1_fish_id is None
        assert result.top1_score == 0.0
        assert result.candidates_evaluated == 0

    def test_nan_embedding_raises(self):
        """NaN in embeddings should raise ValueError."""
        query = np.array([[float("nan")] * 512], dtype=np.float32)
        gallery = {"FISH-A": _make_embedding(seed=1).reshape(1, -1)}

        with pytest.raises(ValueError):
            score_candidates(query, gallery)

    def test_balanced_support_no_unfair_advantage(self):
        """Fish with many supports shouldn't dominate over one with few."""
        fish_a = _make_embedding(seed=10)
        fish_b = _make_embedding(seed=20)

        # A has 50 supports (with slight noise)
        rng = np.random.default_rng(100)
        supports_a = []
        for _ in range(50):
            noise = rng.standard_normal(512).astype(np.float32) * 0.05
            s = fish_a + noise
            s /= np.linalg.norm(s)
            supports_a.append(s)

        # B has 2 supports
        supports_b = [fish_b.copy(), fish_b.copy()]

        gallery = {
            "FISH-A": np.stack(supports_a),
            "FISH-B": np.stack(supports_b),
        }

        # Query is clearly B
        query = fish_b.reshape(1, -1)
        result = score_candidates(query, gallery, max_support_per_identity=8)
        assert result.top1_fish_id == "FISH-B"


class TestDecisionService:
    """Unit tests for identity_decision_service."""

    def _make_context(self, **overrides) -> DecisionContext:
        """Create a default context with overrides."""
        defaults = dict(
            top1_score=0.90,
            top2_score=0.60,
            margin=0.30,
            agreement_ratio=0.80,
            winning_votes=4,
            total_votes=5,
            candidates_evaluated=3,
            minimum_distance_m=2000.0,
            gps_uncertainty_status="guaranteed_inside",
            area_consistency_status="plausible",
            cross_area=False,
            quality_score=0.8,
            valid_crop_count=5,
            track_consistent=True,
            multiple_fish_detected=False,
            calibration_available=True,
            index_complete=True,
            model_version_compatible=True,
        )
        defaults.update(overrides)
        return DecisionContext(**defaults)

    def test_high_confidence_auto_match(self):
        """All conditions met -> auto_match."""
        ctx = self._make_context()
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "auto_match"

    def test_low_score_new_fish(self):
        """Score below review threshold -> new_fish."""
        ctx = self._make_context(top1_score=0.50, margin=0.50)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "new_fish"

    def test_gray_zone_review(self):
        """Score between review and auto thresholds -> needs_manual_review."""
        ctx = self._make_context(top1_score=0.78, margin=0.10)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "needs_manual_review"
        assert result.review_required is True

    def test_insufficient_margin_review(self):
        """High score but tiny margin -> review."""
        ctx = self._make_context(top1_score=0.90, top2_score=0.88, margin=0.02)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "needs_manual_review"

    def test_low_agreement_review(self):
        """High score but low agreement -> review."""
        ctx = self._make_context(agreement_ratio=0.40, winning_votes=2, total_votes=5)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "needs_manual_review"

    def test_multiple_fish_repeat_capture(self):
        """Multiple fish detected -> repeat_capture."""
        ctx = self._make_context(multiple_fish_detected=True)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "repeat_capture"

    def test_low_quality_repeat_capture(self):
        """Quality too low -> repeat_capture."""
        ctx = self._make_context(quality_score=0.1)
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision == "repeat_capture"

    def test_gps_mismatch_blocks_auto_match(self):
        """GPS outside radius should prevent auto_match."""
        ctx = self._make_context(gps_uncertainty_status="outside")
        result = decide_identity(ctx, top1_fish_id="FISH-001")
        assert result.decision != "auto_match"

    def test_no_fish_id_new_fish(self):
        """No top1_fish_id -> new_fish."""
        ctx = self._make_context(candidates_evaluated=0)
        result = decide_identity(ctx, top1_fish_id=None)
        assert result.decision == "new_fish"


class TestPipelineIntegration:
    """Integration tests for the full pipeline."""

    @pytest.fixture
    def pipeline(self, tmp_path, monkeypatch):
        """Create a pipeline with temp database and calibration."""
        import json
        from app.services.identification_pipeline import IdentificationPipeline
        
        db_path = str(tmp_path / "test_emb.sqlite")
        monkeypatch.setattr("app.config.settings.embeddings_db_path", db_path)
        monkeypatch.setattr("app.config.settings.reid_cache_name", "test_model_v1")
        monkeypatch.setattr("app.config.settings.nearby_area_radius_km", 5.0)

        # Create a test calibration file so auto_match is not blocked
        cal_path = tmp_path / "test_calibration.json"
        cal_path.write_text(json.dumps({
            "schema_version": "1",
            "model_version": "test_model_v1",
            "dataset_version": "test_eval",
            "generated_at": "2026-01-01T00:00:00Z",
            "validated": True,
            "validation_far": 0.0005,
            "test_far": 0.0005,
            "global": {
                "review_threshold": 0.70,
                "auto_match_threshold": 0.85,
                "single_candidate_threshold": 0.88,
                "min_margin": 0.05,
                "min_agreement": 0.70,
            },
            "species": {},
        }))
        monkeypatch.setattr("app.config.settings.reid_calibration_path", str(cal_path))

        # Reset singletons
        import app.services.identification_pipeline as pip_mod
        pip_mod._pipeline_instance = None
        import app.services.matching_service as ms_mod
        ms_mod._instance = None
        import app.calibration as cal_mod
        cal_mod._calibration_cache = None

        return IdentificationPipeline()

    def _store_fish(self, pipeline, fish_id, species, lat, lon, seed):
        """Store a fish embedding directly in the matching service."""
        emb = _make_embedding(seed=seed)
        pipeline._matching.store_embedding(
            fish_id=fish_id,
            sighting_id=f"sighting_{seed}",
            species_slug=species,
            area_code="471011",
            embedding=emb,
            latitude=lat,
            longitude=lon,
            model_version="test_model_v1",
        )
        return emb

    def test_new_fish_when_empty_db(self, pipeline):
        """No historical data -> new_fish."""
        query = _make_query_embeddings(n_frames=5, seed=42)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            latitude=BECVA_LAT,
            longitude=BECVA_LON,
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "new_fish"

    def test_auto_match_same_fish(self, pipeline):
        """Query matching stored fish with high score -> auto_match."""
        emb = self._store_fish(pipeline, "FISH-001", "cyprinus_carpio", BECVA_LAT, BECVA_LON, seed=42)

        # Query with the same embedding (5 frames)
        query = np.stack([emb] * 5)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            latitude=BECVA_LAT + 0.001,
            longitude=BECVA_LON,
            gps_accuracy_m=10.0,  # Precise GPS for auto_match
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "auto_match"
        assert result.fish_id == "FISH-001"

    def test_different_species_never_matches(self, pipeline):
        """Different species should find no candidates."""
        self._store_fish(pipeline, "FISH-001", "cyprinus_carpio", BECVA_LAT, BECVA_LON, seed=42)

        query = _make_query_embeddings(n_frames=5, seed=42)
        metadata = CaptureMetadata(
            species_slug="salmo_trutta",
            latitude=BECVA_LAT + 0.001,
            longitude=BECVA_LON,
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "new_fish"
        assert result.fish_id is None

    def test_beyond_5km_no_match(self, pipeline):
        """Fish > 5km away should not be found."""
        self._store_fish(pipeline, "FISH-001", "cyprinus_carpio", BECVA_LAT, BECVA_LON, seed=42)

        query = _make_query_embeddings(n_frames=5, seed=42)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            latitude=BECVA_LAT + 0.10,  # ~11km north
            longitude=BECVA_LON,
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "new_fish"

    def test_no_gps_goes_to_review(self, pipeline):
        """Missing GPS -> needs_manual_review (can't confirm new fish)."""
        query = _make_query_embeddings(n_frames=5, seed=42)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            latitude=None,
            longitude=None,
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "needs_manual_review"

    def test_multiple_fish_repeat_capture(self, pipeline):
        """Multiple fish detected -> repeat_capture regardless of match."""
        self._store_fish(pipeline, "FISH-001", "cyprinus_carpio", BECVA_LAT, BECVA_LON, seed=42)

        query = _make_query_embeddings(n_frames=5, seed=42)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            latitude=BECVA_LAT + 0.001,
            longitude=BECVA_LON,
        )

        result = pipeline.run(query, metadata, multiple_fish_detected=True)
        assert result.decision == "repeat_capture"

    def test_cross_area_detection(self, pipeline):
        """Fish from different area code within 5km -> cross_area=True."""
        self._store_fish(pipeline, "FISH-001", "cyprinus_carpio", BECVA_LAT, BECVA_LON, seed=42)

        # Same embedding, different area code, nearby GPS
        emb = _make_embedding(seed=42)
        query = np.stack([emb] * 5)
        metadata = CaptureMetadata(
            species_slug="cyprinus_carpio",
            area_code="461001",  # Different from 471011
            latitude=BECVA_LAT + 0.001,
            longitude=BECVA_LON,
            gps_accuracy_m=10.0,  # Precise GPS for auto_match
        )

        result = pipeline.run(query, metadata)
        assert result.decision == "auto_match"
        assert result.cross_area is True
