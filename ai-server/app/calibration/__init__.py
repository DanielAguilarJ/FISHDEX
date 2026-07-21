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
    validated: bool = False
    validation_far: Optional[float] = None
    test_far: Optional[float] = None


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
            validated=bool(data.get("validated", False)),
            validation_far=data.get("validation_far"),
            test_far=data.get("test_far"),
        )

        logger.info(
            "Loaded calibration for model %s (dataset=%s, species=%d, validated=%s, val_far=%s, test_far=%s)",
            model_version, _calibration_cache.dataset_version,
            len(species_t), _calibration_cache.validated,
            _calibration_cache.validation_far, _calibration_cache.test_far,
        )
        return _calibration_cache

    except Exception as e:
        logger.error("Failed to load calibration from %s: %s", cal_path, e)
        return None


def is_calibration_valid(cal: Optional[CalibrationData]) -> tuple[bool, str]:
    """Check if calibration meets scientific FAR <= 0.001 criteria for auto_match."""
    if cal is None:
        return False, "No calibration data loaded"
    if not cal.validated:
        return False, f"validated=False for model_version={cal.model_version}"
    if cal.validation_far is None or float(cal.validation_far) > 0.001:
        return False, f"validation_far ({cal.validation_far}) > 0.001"
    if cal.test_far is not None and float(cal.test_far) > 0.001:
        return False, f"test_far ({cal.test_far}) > 0.001"
    return True, "Calibration validated"


def get_thresholds_for_species(
    species_slug: str,
    model_version: str,
) -> tuple[SpeciesThresholds, bool]:
    """
    Get thresholds for a species, with calibration status.
    
    Returns:
        (thresholds, is_calibrated) — if not validated or FAR > 0.001, returns UNCALIBRATED_DEFAULTS and False.
    """
    cal = load_calibration(model_version)
    valid, reason = is_calibration_valid(cal)
    if not valid:
        logger.warning(
            "Calibration for model %s is INVALID for auto_match: %s. Using fallback defaults.",
            model_version, reason,
        )
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
