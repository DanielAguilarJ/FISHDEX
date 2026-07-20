"""
Geographic utilities for FishDex AI Server.

Provides strict Haversine distance calculation between real GPS coordinates.
This module enforces the 5 km radius rule for candidate eligibility.
"""

import math
from typing import Optional


# Earth's mean radius in meters
_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance in meters between two GPS points.

    Args:
        lat1, lon1: Query point (decimal degrees).
        lat2, lon2: Historical point (decimal degrees).

    Returns:
        Distance in meters.

    Raises:
        ValueError: If any coordinate is not finite or out of valid range.
    """
    for name, val, lo, hi in [
        ("lat1", lat1, -90.0, 90.0),
        ("lat2", lat2, -90.0, 90.0),
        ("lon1", lon1, -180.0, 180.0),
        ("lon2", lon2, -180.0, 180.0),
    ]:
        if not math.isfinite(val):
            raise ValueError(f"{name}={val} is not finite")
        if val < lo or val > hi:
            raise ValueError(f"{name}={val} out of range [{lo}, {hi}]")

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def is_within_radius(
    query_lat: Optional[float],
    query_lon: Optional[float],
    historical_lat: Optional[float],
    historical_lon: Optional[float],
    radius_m: float = 5000.0,
) -> tuple[bool, Optional[float]]:
    """
    Check if two GPS points are within the specified radius.

    Returns:
        (within, distance_m) — within is True if distance <= radius_m.
        If either GPS is invalid/missing, returns (False, None).
    """
    if query_lat is None or query_lon is None:
        return (False, None)
    if historical_lat is None or historical_lon is None:
        return (False, None)

    try:
        dist = haversine_m(
            float(query_lat), float(query_lon),
            float(historical_lat), float(historical_lon),
        )
    except (ValueError, TypeError):
        return (False, None)

    return (dist <= radius_m, dist)


def gps_uncertainty_within_radius(
    distance_m: float,
    query_accuracy_m: Optional[float],
    historical_accuracy_m: Optional[float],
    radius_m: float = 5000.0,
) -> str:
    """
    Evaluate GPS uncertainty against the radius constraint.

    Returns one of:
        "guaranteed_inside" — distance + all uncertainty still within radius
        "inside_but_uncertain" — distance within radius but uncertainty crosses it
        "outside" — distance alone exceeds radius
        "unknown" — missing accuracy data
    """
    if distance_m > radius_m:
        return "outside"

    if query_accuracy_m is None or historical_accuracy_m is None:
        return "unknown"

    total_uncertainty = (query_accuracy_m or 0.0) + (historical_accuracy_m or 0.0)
    if distance_m + total_uncertainty <= radius_m:
        return "guaranteed_inside"
    else:
        return "inside_but_uncertain"
