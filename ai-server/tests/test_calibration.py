"""
Tests for Phase 7: Calibration system.
"""
import json
import pytest
from pathlib import Path

from app.calibration import (
    load_calibration,
    get_thresholds_for_species,
    reset_calibration_cache,
    UNCALIBRATED_DEFAULTS,
    SpeciesThresholds,
)


class TestCalibration:
    """Tests for calibration loader."""

    def setup_method(self):
        reset_calibration_cache()

    def test_no_calibration_returns_none(self):
        """Missing calibration file returns None."""
        result = load_calibration("nonexistent_model_v99")
        assert result is None

    def test_uncalibrated_defaults_are_conservative(self):
        """Default thresholds should be conservative (high auto_match bar)."""
        assert UNCALIBRATED_DEFAULTS.auto_match_threshold >= 0.85
        assert UNCALIBRATED_DEFAULTS.min_margin >= 0.05
        assert UNCALIBRATED_DEFAULTS.min_agreement >= 0.70

    def test_get_thresholds_without_calibration(self):
        """Without calibration, returns defaults and is_calibrated=False."""
        thresholds, calibrated = get_thresholds_for_species(
            "cyprinus_carpio", "nonexistent_model"
        )
        assert not calibrated
        assert thresholds == UNCALIBRATED_DEFAULTS

    def test_load_valid_calibration(self, tmp_path, monkeypatch):
        """Valid calibration file loads correctly."""
        cal_data = {
            "schema_version": "1",
            "model_version": "test_model_v1",
            "dataset_version": "eval_2026_01",
            "generated_at": "2026-01-15T10:00:00Z",
            "validated": True,
            "validation_far": 0.0005,
            "test_far": 0.0005,
            "global": {
                "review_threshold": 0.72,
                "auto_match_threshold": 0.89,
                "single_candidate_threshold": 0.92,
                "min_margin": 0.08,
                "min_agreement": 0.78,
            },
            "species": {
                "cyprinus_carpio": {
                    "review_threshold": 0.74,
                    "auto_match_threshold": 0.90,
                    "single_candidate_threshold": 0.93,
                    "min_margin": 0.09,
                    "min_agreement": 0.80,
                }
            },
            "dataset_stats": {
                "total_identities": 50,
                "total_sessions": 200,
            },
        }

        cal_path = tmp_path / "test_model_v1.json"
        cal_path.write_text(json.dumps(cal_data))
        monkeypatch.setattr("app.config.settings.reid_calibration_path", str(cal_path))

        result = load_calibration("test_model_v1")
        assert result is not None
        assert result.model_version == "test_model_v1"
        assert result.global_thresholds.auto_match_threshold == 0.89
        assert "cyprinus_carpio" in result.species_thresholds

    def test_species_specific_thresholds(self, tmp_path, monkeypatch):
        """Species-specific thresholds override globals."""
        cal_data = {
            "schema_version": "1",
            "model_version": "test_model_v1",
            "dataset_version": "eval_2026_01",
            "generated_at": "2026-01-15T10:00:00Z",
            "validated": True,
            "validation_far": 0.0005,
            "test_far": 0.0005,
            "global": {
                "review_threshold": 0.72,
                "auto_match_threshold": 0.89,
                "single_candidate_threshold": 0.92,
                "min_margin": 0.08,
                "min_agreement": 0.78,
            },
            "species": {
                "cyprinus_carpio": {
                    "review_threshold": 0.74,
                    "auto_match_threshold": 0.90,
                    "single_candidate_threshold": 0.93,
                    "min_margin": 0.09,
                    "min_agreement": 0.80,
                }
            },
        }

        cal_path = tmp_path / "test_model_v1.json"
        cal_path.write_text(json.dumps(cal_data))
        monkeypatch.setattr("app.config.settings.reid_calibration_path", str(cal_path))

        thresholds, calibrated = get_thresholds_for_species("cyprinus_carpio", "test_model_v1")
        assert calibrated
        assert thresholds.auto_match_threshold == 0.90

        # Unknown species falls back to global
        thresholds2, calibrated2 = get_thresholds_for_species("salmo_trutta", "test_model_v1")
        assert calibrated2
        assert thresholds2.auto_match_threshold == 0.89  # Global

    def test_model_version_mismatch_rejected(self, tmp_path, monkeypatch):
        """Calibration for wrong model is rejected."""
        cal_data = {
            "schema_version": "1",
            "model_version": "old_model_v0",
            "global": {
                "review_threshold": 0.72,
                "auto_match_threshold": 0.89,
                "single_candidate_threshold": 0.92,
                "min_margin": 0.08,
                "min_agreement": 0.78,
            },
        }

        cal_path = tmp_path / "cal.json"
        cal_path.write_text(json.dumps(cal_data))
        monkeypatch.setattr("app.config.settings.reid_calibration_path", str(cal_path))

        result = load_calibration("new_model_v2")
        assert result is None
