"""
Tests for Phase 5: Czech area service validation.
"""
import pytest

from app.services.czech_area_service import (
    resolve_area,
    validate_area_code,
    evaluate_area_gps_consistency,
    suggest_areas,
)


class TestCzechAreaValidation:
    """Tests for area code validation."""

    def test_valid_code_resolves(self):
        """Known area code resolves to area data."""
        area = resolve_area("471011")
        assert area is not None
        assert "BEČVA" in area["name"].upper() or "Bečva" in area["name"]

    def test_code_with_separators_normalizes(self):
        """Hyphens and spaces are stripped."""
        area = resolve_area("471-011")
        assert area is not None
        area2 = resolve_area("471 011")
        assert area2 is not None

    def test_unknown_code_returns_none(self):
        """Non-existent code returns None."""
        assert resolve_area("999999") is None

    def test_invalid_format_detected(self):
        """Non-6-digit codes are invalid."""
        valid, msg = validate_area_code("ABC")
        assert not valid
        assert "format" in msg.lower() or "digit" in msg.lower()

    def test_empty_code_invalid(self):
        """Empty code is invalid."""
        valid, msg = validate_area_code("")
        assert not valid

    def test_valid_format_but_unknown(self):
        """6-digit code not in catalog."""
        valid, msg = validate_area_code("999999")
        assert not valid
        assert "unknown" in msg.lower() or "Unknown" in msg

    def test_471011_with_prague_is_mismatch(self):
        """Area 471011 (BEČVA 5 in Moravia) with Prague GPS = mismatch."""
        status = evaluate_area_gps_consistency("471011", 50.087, 14.421)
        assert status == "mismatch"

    def test_471011_with_correct_gps_is_plausible(self):
        """Area 471011 with actual BEČVA coordinates = plausible."""
        status = evaluate_area_gps_consistency("471011", 49.529, 17.788)
        assert status == "plausible"

    def test_invalid_code_unverifiable(self):
        """Invalid code returns unverifiable."""
        status = evaluate_area_gps_consistency("INVALID", 50.0, 14.0)
        assert status == "unverifiable"

    def test_suggest_areas_returns_nearby(self):
        """Suggestions near BEČVA return relevant areas."""
        suggestions = suggest_areas(49.529, 17.788, max_results=5)
        assert len(suggestions) > 0
        assert len(suggestions) <= 5
        # First suggestion should be very close
        assert suggestions[0]["distance_km"] < 50

    def test_suggest_areas_includes_code(self):
        """Each suggestion has the required fields."""
        suggestions = suggest_areas(49.529, 17.788, max_results=3)
        for s in suggestions:
            assert "code" in s
            assert "name" in s
            assert "distance_km" in s
