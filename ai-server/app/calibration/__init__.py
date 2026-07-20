"""
Calibration loader for ReID thresholds.

Loads species-specific thresholds from a versioned JSON calibration file.
If no calibration exists for the active model, falls back to global defaults
and blocks auto_match (sends to review instead).
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeciesThresholds:
    """Calibrated thresholds for a specific species."""
    review_threshold: float
    auto_match_threshold: float
    single_candidate_threshold: float
    min_margin: float
    min_agreement: float


@dataclass(frozen=True)
class CalibrationData:
    """Complete calibration for a model version."""
    schema_version: str
    model_version: str
    dataset_version: str
    generated_at: str
    global_thresholds: SpeciesThresholds
    species_thresholds: dict[str, SpeciesThresholds]
    dataset_stats: dict  # identities, sessions, pairs per species


# Default uncalibrated thresholds — conservative
UNCALIBRATED_DEFAULTS = SpeciesThresholds(
    review_threshold=0.70,
    auto_match_threshold=0.88,
    single_candidate_threshold=0.91,
    min_margin=0.07,
    min_agreement=0.75,
)


_calibration_cache: Optional[CalibrationData] = None


def load_calibration(model_version: str) -> Optional[CalibrationData]:
    """
    Load calibration data for the given model version.
    
    Searches for:
    1. FISHDEX_REID_CALIBRATION_PATH env/setting
    2. calibration/ directory next to the model
    3. Returns None if no compatible calibration exists
    """
    global _calibration_cache
    
    if _calibration_cache is not None and _calibration_cache.model_version == model_version:
        return _calibration_cache

    cal_path = getattr(settings, "reid_calibration_path", None)
    if not cal_path:
        cal_path = Path("calibration") / f"{model_version}.json"
    else:
        cal_path = Path(cal_path)

    if not cal_path.exists():
        logger.warning(
            "No calibration file found for model %s at %s — "
            "auto_match disabled, all matches go to review",
            model_version, cal_path,
        )
        return None

    try:
        data = json.loads(cal_path.read_text())
        
        if data.get("model_version") != model_version:
            logger.error(
                "Calibration model_version mismatch: file=%s active=%s",
                data.get("model_version"), model_version,
            )
            return None

        global_t = data["global"]
        global_thresholds = SpeciesThresholds(
            review_threshold=global_t["review_threshold"],
            auto_match_threshold=global_t["auto_match_threshold"],
            single_candidate_threshold=global_t["single_candidate_threshold"],
            min_margin=global_t["min_margin"],
            min_agreement=global_t["min_agreement"],
        )

        species_t = {}
        for slug, vals in data.get("species", {}).items():
            species_t[slug] = SpeciesThresholds(
                review_threshold=vals["review_threshold"],
                auto_match_threshold=vals["auto_match_threshold"],
                single_candidate_threshold=vals["single_candidate_threshold"],
                min_margin=vals["min_margin"],
                min_agreement=vals["min_agreement"],
            )

        _calibration_cache = CalibrationData(
            schema_version=data.get("schema_version", "1"),
            model_version=data["model_version"],
            dataset_version=data.get("dataset_version", "unknown"),
            generated_at=data.get("generated_at", "unknown"),
            global_thresholds=global_thresholds,
            species_thresholds=species_t,
            dataset_stats=data.get("dataset_stats", {}),
        )

        logger.info(
            "Loaded calibration for model %s (dataset=%s, species=%d)",
            model_version, _calibration_cache.dataset_version,
            len(species_t),
        )
        return _calibration_cache

    except Exception as e:
        logger.error("Failed to load calibration from %s: %s", cal_path, e)
        return None


def get_thresholds_for_species(
    species_slug: str,
    model_version: str,
) -> tuple[SpeciesThresholds, bool]:
    """
    Get thresholds for a species, with calibration status.
    
    Returns:
        (thresholds, is_calibrated) — if not calibrated, returns UNCALIBRATED_DEFAULTS
    """
    cal = load_calibration(model_version)
    
    if cal is None:
        return (UNCALIBRATED_DEFAULTS, False)

    species_t = cal.species_thresholds.get(species_slug)
    if species_t:
        return (species_t, True)

    # Fall back to global calibrated thresholds
    return (cal.global_thresholds, True)


def reset_calibration_cache():
    """Reset the calibration cache (for testing)."""
    global _calibration_cache
    _calibration_cache = None
