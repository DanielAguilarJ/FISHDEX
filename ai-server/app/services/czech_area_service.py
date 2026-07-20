"""
Czech Area Service for FishDex.

Provides area code validation, lookup, suggestion, and GPS consistency checks.
Uses the existing CZECH_AREAS catalog from app.data.czech_areas.
"""

import logging
import re

from app.data.czech_areas import CZECH_AREAS, find_nearest_areas
from app.utils.area_utils import normalize_area_code as _normalize_area_code
from app.utils.geo import haversine_m

logger = logging.getLogger(__name__)

# Build O(1) lookup index: normalized code -> area entry
_AREA_INDEX: dict[str, dict] = {
    area["code_clean"]: area for area in CZECH_AREAS
}

_CODE_PATTERN = re.compile(r"^\d{6}$")


def normalize_area_code(area_code: str | None) -> str:
    """Import and delegate to existing app.utils.area_utils.normalize_area_code."""
    return _normalize_area_code(area_code)


def resolve_area(area_code: str) -> dict | None:
    """
    Look up a Czech fishing area by code.

    Normalizes the code (strip spaces/hyphens, uppercase), validates it's
    exactly 6 digits, then performs O(1) lookup in the area index.

    Args:
        area_code: Raw area code string (e.g. "471 011", "471-011", "471011").

    Returns:
        The area dict from CZECH_AREAS or None if not found.
    """
    normalized = normalize_area_code(area_code)
    if not _CODE_PATTERN.match(normalized):
        return None
    return _AREA_INDEX.get(normalized)


def validate_area_code(area_code: str) -> tuple[bool, str]:
    """
    Validate a Czech fishing area code.

    Args:
        area_code: Raw area code string to validate.

    Returns:
        Tuple of (is_valid, error_message). error_message is empty string when valid.
    """
    if not area_code or not area_code.strip():
        return False, "Empty area code"

    normalized = normalize_area_code(area_code)
    if not _CODE_PATTERN.match(normalized):
        return False, "Invalid format (must be 6 digits)"

    if normalized not in _AREA_INDEX:
        return False, f"Unknown area code: {normalized}"

    return True, ""


def suggest_areas(
    latitude: float, longitude: float, max_results: int = 5
) -> list[dict]:
    """
    Suggest nearby fishing areas based on GPS coordinates.

    Uses find_nearest_areas with a generous radius to find candidates,
    then returns the closest ones formatted for API consumption.

    Args:
        latitude: GPS latitude.
        longitude: GPS longitude.
        max_results: Maximum number of suggestions to return.

    Returns:
        List of dicts with keys: code, name, distance_km, region.
    """
    # Use a large radius to ensure we get enough candidates
    nearby = find_nearest_areas(
        lat=latitude, lon=longitude, max_distance_km=100.0, limit=max_results
    )

    results: list[dict] = []
    for area in nearby:
        results.append({
            "code": area["code_clean"],
            "name": area["name"],
            "distance_km": area["distance_km"],
            "region": area["region_code"],
        })

    return results


def evaluate_area_gps_consistency(
    area_code: str, latitude: float, longitude: float
) -> str:
    """
    Evaluate whether a GPS position is consistent with the claimed fishing area.

    Without official area polygons, we can only detect extreme inconsistencies
    by comparing the GPS point to the known reference coordinate of the area.

    Args:
        area_code: The claimed fishing area code.
        latitude: GPS latitude of the catch/observation.
        longitude: GPS longitude of the catch/observation.

    Returns:
        One of:
        - "plausible": distance <= 50 km (reasonable for Czech fishing areas
          which can be along rivers)
        - "plausible": distance 50-100 km (still plausible but logged as warning)
        - "mismatch": distance > 100 km (extreme inconsistency)
        - "unverifiable": area has no coordinates in catalog
        - "user_confirmed": reserved for future use when user explicitly confirms
    """
    area = resolve_area(area_code)
    if area is None:
        logger.warning(
            "evaluate_area_gps_consistency: area code %s not found in catalog",
            area_code,
        )
        return "unverifiable"

    area_lat = area.get("lat")
    area_lon = area.get("lon")

    if area_lat is None or area_lon is None:
        logger.debug(
            "Area %s has no coordinates, cannot verify GPS consistency",
            area_code,
        )
        return "unverifiable"

    # haversine_m returns meters, convert to km
    distance_m = haversine_m(latitude, longitude, area_lat, area_lon)
    distance_km = distance_m / 1000.0

    if distance_km > 100.0:
        logger.info(
            "GPS mismatch for area %s: %.1f km from area reference point",
            area_code,
            distance_km,
        )
        return "mismatch"

    if distance_km > 50.0:
        logger.warning(
            "GPS marginally consistent for area %s: %.1f km from reference "
            "(within tolerance but noteworthy)",
            area_code,
            distance_km,
        )

    return "plausible"
