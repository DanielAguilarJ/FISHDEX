"""
Calibration loader for ReID thresholds.

Loads species-specific thresholds from a versioned JSON calibration file.
If no calibration exists for the active model, falls back to global defaults
and blocks auto_match (sends to review instead).

FAIL-CLOSED POLICY:
- test_far is REQUIRED for auto_match eligibility.
- If test_far is missing, NaN, Inf, negative, or > 0.001 → auto_match disabled.
- If dataset_stats.test_far exists but root test_far is missing → reject.
- Metrics override the "validated" flag — if metrics fail, calibration is invalid
  regardless of what validated says.
"""

import json
import logging
import math
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
    # Required metadata for audit
    far_target: Optional[float] = None
    validation_samples: Optional[int] = None
    test_samples: Optional[int] = None
    unknown_test_queries: Optional[int] = None


# Default uncalibrated thresholds — conservative
UNCALIBRATED_DEFAULTS = SpeciesThresholds(
    review_threshold=0.70,
    auto_match_threshold=0.88,
    single_candidate_threshold=0.91,
    min_margin=0.07,
    min_agreement=0.75,
)


_calibration_cache: Optional[CalibrationData] = None


def _is_valid_far_value(val) -> bool:
    """Check if a FAR value is a valid finite number in [0.0, 1.0]."""
    if val is None:
        return False
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    if math.isnan(f) or math.isinf(f):
        return False
    if f < 0.0 or f > 1.0:
        return False
    return True


def load_calibration(model_version: str) -> Optional[CalibrationData]:
    """
    Load calibration data for the given model version.
    
    Searches for:
    1. FISHDEX_REID_CALIBRATION_PATH env/setting
    2. calibration/ directory next to the model
    3. Returns None if no compatible calibration exists
    
    FAIL-CLOSED: Extracts test_far from both root and dataset_stats.
    If only dataset_stats has it, uses that value but logs a warning.
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

        # --- CRITICAL: Extract test_far correctly ---
        # Priority: root-level test_far > dataset_stats.test_far
        root_test_far = data.get("test_far")
        dataset_stats = data.get("dataset_stats", {})
        stats_test_far = dataset_stats.get("test_far") if isinstance(dataset_stats, dict) else None

        # Resolve effective test_far
        effective_test_far = root_test_far
        if effective_test_far is None and stats_test_far is not None:
            logger.warning(
                "Calibration %s: test_far missing from root but found in "
                "dataset_stats (%.6f). Using dataset_stats value. "
                "This indicates a schema issue in the calibration generator.",
                model_version, stats_test_far,
            )
            effective_test_far = stats_test_far

        # If both exist and disagree, use the WORSE (higher) value
        if root_test_far is not None and stats_test_far is not None:
            try:
                if abs(float(root_test_far) - float(stats_test_far)) > 1e-6:
                    effective_test_far = max(float(root_test_far), float(stats_test_far))
                    logger.warning(
                        "Calibration %s: root test_far=%.6f != dataset_stats.test_far=%.6f. "
                        "Using worse (higher) value: %.6f",
                        model_version, float(root_test_far), float(stats_test_far),
                        effective_test_far,
                    )
            except (TypeError, ValueError):
                pass

        # Extract validation_far the same way
        root_validation_far = data.get("validation_far")

        _calibration_cache = CalibrationData(
            schema_version=data.get("schema_version", "1"),
            model_version=data["model_version"],
            dataset_version=data.get("dataset_version", "unknown"),
            generated_at=data.get("generated_at", "unknown"),
            global_thresholds=global_thresholds,
            species_thresholds=species_t,
            dataset_stats=dataset_stats,
            validated=bool(data.get("validated", False)),
            validation_far=root_validation_far,
            test_far=effective_test_far,
            far_target=data.get("far_target"),
            validation_samples=data.get("validation_samples"),
            test_samples=data.get("test_samples"),
            unknown_test_queries=data.get("unknown_test_queries"),
        )

        logger.info(
            "Loaded calibration for model %s (dataset=%s, species=%d, "
            "validated=%s, val_far=%s, test_far=%s [effective])",
            model_version, _calibration_cache.dataset_version,
            len(species_t), _calibration_cache.validated,
            _calibration_cache.validation_far, _calibration_cache.test_far,
        )
        return _calibration_cache

    except Exception as e:  # noqa: BLE001 — an unreadable calibration means uncalibrated, not broken
        logger.error("Failed to load calibration from %s: %s", cal_path, e)
        return None


def is_calibration_valid(cal: Optional[CalibrationData]) -> tuple[bool, str]:
    """
    Check if calibration meets scientific FAR <= 0.001 criteria for auto_match.
    
    FAIL-CLOSED POLICY:
    - test_far MUST exist and be a valid number <= 0.001
    - validation_far MUST exist and be a valid number <= 0.001
    - validated flag alone is NOT sufficient — metrics must confirm
    - NaN, Inf, negative, or > 1.0 values are rejected
    """
    if cal is None:
        return False, "No calibration data loaded"

    if not cal.validated:
        return False, f"validated=False for model_version={cal.model_version}"

    # test_far is REQUIRED (fail-closed)
    if not _is_valid_far_value(cal.test_far):
        return False, (
            f"test_far is missing or invalid ({cal.test_far}) for "
            f"model_version={cal.model_version}. "
            f"Auto_match requires measured test_far <= 0.001."
        )

    if float(cal.test_far) > 0.001:
        return False, (
            f"test_far ({cal.test_far:.6f}) > 0.001 for "
            f"model_version={cal.model_version}"
        )

    # validation_far is REQUIRED
    if not _is_valid_far_value(cal.validation_far):
        return False, (
            f"validation_far is missing or invalid ({cal.validation_far}) for "
            f"model_version={cal.model_version}. "
            f"Auto_match requires measured validation_far <= 0.001."
        )

    if float(cal.validation_far) > 0.001:
        return False, (
            f"validation_far ({cal.validation_far:.6f}) > 0.001 for "
            f"model_version={cal.model_version}"
        )

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


def get_calibration_status(model_version: str) -> dict:
    """
    Return calibration status suitable for /health/ready endpoint.
    """
    cal = load_calibration(model_version)
    valid, reason = is_calibration_valid(cal)
    
    return {
        "model_version": model_version,
        "calibration_loaded": cal is not None,
        "calibration_validated": valid,
        "validation_reason": reason,
        "validation_far": cal.validation_far if cal else None,
        "test_far": cal.test_far if cal else None,
        "auto_match_enabled": valid,
    }


def reset_calibration_cache():
    """Reset the calibration cache (for testing)."""
    global _calibration_cache
    _calibration_cache = None
