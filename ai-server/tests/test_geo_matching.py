"""
Test suite for geographic eligibility and decision logic (Fase 1).

Tests the strict 5 km radius rule:
- same_area NEVER bypasses GPS radius
- different area within 5 km IS eligible (cross_area)
- same area beyond 5 km IS excluded
- missing GPS prevents auto-match
- different species never participates
"""

import math
import pytest
import numpy as np

from app.utils.geo import haversine_m, is_within_radius, gps_uncertainty_within_radius


# --- Known reference points ---
# 471011 = BEČVA 5, approximately: 49.529612, 17.788836
BECVA_5_LAT = 49.529612
BECVA_5_LON = 17.788836

# A point ~4.99 km from BEČVA 5 (calculated)
# Moving ~4.99 km north at this latitude: delta_lat ≈ 0.0449°
POINT_4_99KM_LAT = 49.529612 + 0.0449
POINT_4_99KM_LON = 17.788836

# A point ~5.01 km from BEČVA 5
POINT_5_01KM_LAT = 49.529612 + 0.0451
POINT_5_01KM_LON = 17.788836

# Prague coordinates (Old Town): 50.087, 14.421
PRAGUE_LAT = 50.087
PRAGUE_LON = 14.421


class TestHaversine:
    """Unit tests for haversine_m distance calculation."""

    def test_same_point_returns_zero(self):
        assert haversine_m(50.0, 14.0, 50.0, 14.0) == 0.0

    def test_known_distance_prague_to_brno(self):
        # Prague to Brno is approximately 185 km
        dist = haversine_m(50.075, 14.437, 49.195, 16.608)
        assert 180_000 < dist < 190_000

    def test_short_distance_accuracy(self):
        # 1 degree latitude ≈ 111.32 km
        dist = haversine_m(49.0, 17.0, 50.0, 17.0)
        assert 110_000 < dist < 112_000

    def test_invalid_latitude_raises(self):
        with pytest.raises(ValueError):
            haversine_m(91.0, 14.0, 50.0, 14.0)

    def test_invalid_longitude_raises(self):
        with pytest.raises(ValueError):
            haversine_m(50.0, 181.0, 50.0, 14.0)

    def test_nan_raises(self):
        with pytest.raises(ValueError):
            haversine_m(float("nan"), 14.0, 50.0, 14.0)

    def test_inf_raises(self):
        with pytest.raises(ValueError):
            haversine_m(float("inf"), 14.0, 50.0, 14.0)


class TestIsWithinRadius:
    """Unit tests for the GPS radius eligibility check."""

    def test_same_point_within(self):
        within, dist = is_within_radius(50.0, 14.0, 50.0, 14.0, radius_m=5000.0)
        assert within is True
        assert dist == 0.0

    def test_4_99km_within(self):
        within, dist = is_within_radius(
            BECVA_5_LAT, BECVA_5_LON,
            POINT_4_99KM_LAT, POINT_4_99KM_LON,
            radius_m=5000.0,
        )
        assert within is True
        assert dist is not None
        assert dist < 5000.0

    def test_5_01km_excluded(self):
        within, dist = is_within_radius(
            BECVA_5_LAT, BECVA_5_LON,
            POINT_5_01KM_LAT, POINT_5_01KM_LON,
            radius_m=5000.0,
        )
        assert within is False
        assert dist is not None
        assert dist > 5000.0

    def test_missing_query_gps_returns_false(self):
        within, dist = is_within_radius(
            None, None, BECVA_5_LAT, BECVA_5_LON, radius_m=5000.0
        )
        assert within is False
        assert dist is None

    def test_missing_historical_gps_returns_false(self):
        within, dist = is_within_radius(
            BECVA_5_LAT, BECVA_5_LON, None, None, radius_m=5000.0
        )
        assert within is False
        assert dist is None

    def test_prague_to_becva_excluded(self):
        """471011 is BEČVA 5, not in Prague. Distance ~240 km."""
        within, dist = is_within_radius(
            PRAGUE_LAT, PRAGUE_LON,
            BECVA_5_LAT, BECVA_5_LON,
            radius_m=5000.0,
        )
        assert within is False
        assert dist is not None
        assert dist > 200_000  # > 200 km

    def test_20km_same_code_excluded(self):
        """Same revír code but 20 km away: MUST be excluded."""
        # 20 km north of BEČVA 5
        far_lat = BECVA_5_LAT + 0.18  # ~20 km
        within, dist = is_within_radius(
            BECVA_5_LAT, BECVA_5_LON,
            far_lat, BECVA_5_LON,
            radius_m=5000.0,
        )
        assert within is False
        assert dist > 19_000


class TestGpsUncertainty:
    """Tests for GPS uncertainty evaluation."""

    def test_guaranteed_inside(self):
        result = gps_uncertainty_within_radius(
            distance_m=3000.0,
            query_accuracy_m=500.0,
            historical_accuracy_m=500.0,
            radius_m=5000.0,
        )
        assert result == "guaranteed_inside"

    def test_inside_but_uncertain(self):
        result = gps_uncertainty_within_radius(
            distance_m=4500.0,
            query_accuracy_m=400.0,
            historical_accuracy_m=400.0,
            radius_m=5000.0,
        )
        assert result == "inside_but_uncertain"

    def test_outside(self):
        result = gps_uncertainty_within_radius(
            distance_m=5100.0,
            query_accuracy_m=10.0,
            historical_accuracy_m=10.0,
            radius_m=5000.0,
        )
        assert result == "outside"

    def test_unknown_when_missing_accuracy(self):
        result = gps_uncertainty_within_radius(
            distance_m=3000.0,
            query_accuracy_m=None,
            historical_accuracy_m=50.0,
            radius_m=5000.0,
        )
        assert result == "unknown"


class TestMatchingServiceGeoStrict:
    """
    Integration tests for MatchingService.find_match with strict GPS rules.
    Uses a temporary SQLite database with synthetic embeddings.
    """

    @pytest.fixture
    def matching_service(self, tmp_path, monkeypatch):
        """Create a MatchingService with a temp database."""
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

    def test_same_code_4_99km_eligible(self, matching_service):
        """Same area code, 4.99 km: should be eligible for matching."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=POINT_4_99KM_LAT, longitude=POINT_4_99KM_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] == "FISH-001"
        assert result["score"] > 0.99  # Same embedding

    def test_same_code_5_01km_excluded(self, matching_service):
        """Same area code, 5.01 km: MUST be excluded."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=POINT_5_01KM_LAT, longitude=POINT_5_01KM_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None
        assert result["candidates_evaluated"] == 0

    def test_different_code_1km_eligible_cross_area(self, matching_service):
        """Different area code but within 1 km: eligible as cross_area."""
        emb = self._random_embedding(seed=42)
        # Store in area 471011
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        # Query from a different area code but ~500m away
        query_lat = BECVA_5_LAT + 0.004  # ~450m
        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="461001",
            threshold=0.70,
            latitude=query_lat, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] == "FISH-001"
        assert result["decision_context"]["cross_area"] is True

    def test_same_code_20km_excluded(self, matching_service):
        """Same area code, 20 km away: MUST be excluded (same_area does NOT bypass)."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        # 20 km north — same area code
        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=BECVA_5_LAT + 0.18, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None

    def test_different_species_excluded(self, matching_service):
        """Different species within 100m: NEVER participates."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="salmo_trutta", area_code="471011",
            threshold=0.70,
            latitude=BECVA_5_LAT + 0.0001, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None
        assert result["candidates_evaluated"] == 0

    def test_missing_query_gps_no_automatch(self, matching_service):
        """No GPS from query: cannot auto-match."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=None, longitude=None,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None
        assert result["decision_context"]["reason"] == "missing_query_gps"

    def test_missing_historical_gps_excluded(self, matching_service):
        """Historical embedding without GPS: excluded from matching."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=None, longitude=None,  # No GPS stored
            model_version="test_model_v1",
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None

    def test_incompatible_model_version_excluded(self, matching_service):
        """Embeddings from a different model version: excluded."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="old_model_v0",  # Different version
        )

        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=BECVA_5_LAT + 0.001, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] is None
        assert result["candidates_evaluated"] == 0

    def test_invalid_area_code_still_matches_by_gps(self, matching_service):
        """Invalid/unknown area code doesn't block matching if GPS is valid."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        # Query with a garbage area code but valid nearby GPS
        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="INVALID",
            threshold=0.70,
            latitude=BECVA_5_LAT + 0.001, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] == "FISH-001"

    def test_top2_and_margin(self, matching_service):
        """Verify top-2 scoring and margin calculation."""
        emb1 = self._random_embedding(seed=10)
        emb2 = self._random_embedding(seed=20)

        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb1,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        matching_service.store_embedding(
            fish_id="FISH-002", sighting_id="s2", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb2,
            latitude=BECVA_5_LAT + 0.001, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        # Query with emb1 — should match FISH-001 with high score
        result = matching_service.find_match(
            embedding=emb1, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=BECVA_5_LAT + 0.002, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )
        assert result["fish_id"] == "FISH-001"
        assert result["top2_fish_id"] == "FISH-002"
        assert result["margin"] > 0
        assert result["candidates_evaluated"] == 2

    def test_471011_with_prague_gps_inconsistency(self, matching_service):
        """Area 471011 with Prague GPS: should NOT find historical BEČVA fish."""
        emb = self._random_embedding(seed=42)
        matching_service.store_embedding(
            fish_id="FISH-001", sighting_id="s1", species_slug="cyprinus_carpio",
            area_code="471011", embedding=emb,
            latitude=BECVA_5_LAT, longitude=BECVA_5_LON,
            model_version="test_model_v1",
        )

        # Query claims area 471011 but GPS is in Prague (~240 km away)
        result = matching_service.find_match(
            embedding=emb, species_slug="cyprinus_carpio", area_code="471011",
            threshold=0.70,
            latitude=PRAGUE_LAT, longitude=PRAGUE_LON,
            model_version="test_model_v1",
        )
        # Must NOT match because GPS distance > 5 km
        assert result["fish_id"] is None
