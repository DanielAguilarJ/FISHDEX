"""
FishDex AI Server - Reference data and legacy identification endpoint
====================================================================
GET  /api/v1/areas/search           — nearby fishing areas (public reference data)
GET  /api/v1/areas/{code}/species   — species recorded in an area
GET  /api/v1/areas/{code}/stats     — aggregate statistics for an area
GET  /api/v1/species                — full Czech species catalog
GET  /api/v1/fish/{fish_id}/history — catch history (researchers/admins only)
POST /api/v1/identify               — retired; returns 410

The canonical identification flow is ``POST /api/v1/jobs/upload``, which runs
:class:`~app.services.identification_pipeline.IdentificationPipeline` with
calibration gating, contamination protection and concurrency safety. The legacy
inline pipeline that used to live here lacked all three, so it was retired; the
unreachable implementation has been removed rather than left in place.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.routers.auth import ELEVATED_ROLES, get_current_user
from app.services.storage_service import get_area_stats, get_species_in_area

logger = logging.getLogger(__name__)

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]

# Guard rails for the public area search endpoint.
MIN_SEARCH_RADIUS_KM = 0.1
MAX_SEARCH_RADIUS_KM = 100.0


# =========================================================================
# POST /api/v1/identify — retired
# =========================================================================
@router.post(
    "/identify",
    status_code=status.HTTP_410_GONE,
    summary="Retired — use POST /api/v1/jobs/upload",
    description=(
        "This endpoint has been retired. The legacy pipeline lacked calibration "
        "gating and could contaminate the identity gallery."
    ),
)
async def identify_fish() -> None:
    """
    Reject calls to the retired identification endpoint.

    Raises:
        HTTPException 410: Always. Clients must use ``POST /api/v1/jobs/upload``.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "This endpoint has been retired. "
            "Use POST /api/v1/jobs/upload for fish identification. "
            "The legacy pipeline lacked calibration gating and could "
            "contaminate the identity gallery."
        ),
    )


# =========================================================================
# GET /api/v1/fish/{fish_id}/history
# =========================================================================
@router.get(
    "/fish/{fish_id}/history",
    summary="Get catch history for a fish",
    description=(
        "Returns the full catch history for a specific fish. Restricted to "
        "researchers and admins because the history discloses recapture locations."
    ),
)
async def get_fish_history_endpoint(
    fish_id: str,
    requester: CurrentUser,
) -> dict[str, Any]:
    """
    Look up a fish by id and return its complete catch history.

    The caller's role is read from the database. It used to be taken from a
    ``user_role`` query parameter, which let any anonymous client request
    ``user_role=researcher`` and receive GPS coordinates.

    Args:
        fish_id: Unique fish identifier, e.g. ``CZ-401001-CYPCA-0001``.
        requester: Authenticated user record.

    Returns:
        Dict with ``fish_id``, ``area_code``, ``species_slug``, ``total_catches``
        and the ``history`` list.

    Raises:
        HTTPException 403: Caller lacks an elevated role.
        HTTPException 404: Fish not found.
    """
    if requester.get("role") not in ELEVATED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El historial completo está disponible solo para Researchers y Admins",
        )

    from app.services.storage_service import get_fish_history_by_id

    result = get_fish_history_by_id(fish_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Fish {fish_id} not found"
        )
    return result


# =========================================================================
# GET /api/v1/areas/{area_code}/stats
# =========================================================================
@router.get(
    "/areas/{area_code}/stats",
    summary="Get area statistics",
    description=(
        "Returns total fish count, species breakdown and most recent catch date "
        "for an area. Aggregate only — no individual fish locations."
    ),
)
async def get_area_stats_endpoint(area_code: str, requester: CurrentUser) -> dict[str, Any]:
    """
    Compute aggregate statistics for a fishing area.

    Args:
        area_code: Czech fishing area code, with or without a space.
        requester: Authenticated user record.

    Returns:
        Dict with ``total_fish``, ``species_breakdown``, ``most_recent_catch``,
        ``total_catches`` and, when resolvable, ``area_name``.
    """
    stats = get_area_stats(area_code)

    try:
        from app.data.czech_areas import find_area_by_code

        area_info = find_area_by_code(area_code)
        if area_info:
            stats["area_name"] = area_info["name"]
    except (KeyError, ValueError) as exc:
        # Enrichment is best-effort; a missing catalog entry is not an error.
        logger.warning("Could not resolve area name for %s: %s", area_code, exc)

    return stats


# =========================================================================
# GET /api/v1/areas/search
# =========================================================================
@router.get(
    "/areas/search",
    summary="Search nearby fishing areas",
    description="Find fishing areas near GPS coordinates using Haversine distance.",
)
async def search_areas(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of current position"),
    lon: float = Query(
        ..., ge=-180.0, le=180.0, description="Longitude of current position"
    ),
    radius_km: float = Query(
        10.0,
        ge=MIN_SEARCH_RADIUS_KM,
        le=MAX_SEARCH_RADIUS_KM,
        description="Search radius in kilometres",
    ),
) -> dict[str, Any]:
    """
    Search for fishing areas near the given coordinates.

    This is public reference data (the official Czech revír catalog); it contains
    no user or individual-fish information.

    Args:
        lat: Latitude, validated to [-90, 90] by FastAPI.
        lon: Longitude, validated to [-180, 180] by FastAPI.
        radius_km: Maximum search radius, validated to [0.1, 100].

    Returns:
        Dict with ``areas``, ``count`` and the echoed ``radius_km``.
    """
    from app.data.czech_areas import find_nearest_areas

    areas = find_nearest_areas(lat, lon, max_distance_km=radius_km)
    return {"areas": areas, "count": len(areas), "radius_km": radius_km}


# =========================================================================
# GET /api/v1/areas/{area_code}/species
# =========================================================================
@router.get(
    "/areas/{area_code}/species",
    summary="Get species recorded in an area",
    description="Returns the unique species recorded in storage for this area.",
)
async def get_area_species(area_code: str, requester: CurrentUser) -> dict[str, Any]:
    """
    List the species recorded in a specific fishing area.

    Args:
        area_code: Czech fishing area code, with or without a space.
        requester: Authenticated user record.

    Returns:
        Dict with ``area_code``, ``species`` and ``count``.
    """
    from app.data.czech_species import find_species_by_name

    species_slugs = get_species_in_area(area_code)

    species_list: list[dict[str, Any]] = []
    for slug in species_slugs:
        readable = slug.replace("_", " ").title()
        info = find_species_by_name(readable)
        species_list.append(info or {"slug": slug, "english_name": readable})

    return {"area_code": area_code, "species": species_list, "count": len(species_list)}


# =========================================================================
# GET /api/v1/species
# =========================================================================
@router.get(
    "/species",
    summary="Get all Czech fish species",
    description="Returns the complete Czech fish species catalog for dropdowns.",
)
async def get_all_species() -> dict[str, Any]:
    """
    Return the complete Czech fish species catalog.

    Public: static reference data with no user or location content.

    Returns:
        Dict with ``species`` and ``count``.
    """
    from app.data.czech_species import get_all_species as load_all_species

    species = load_all_species()
    return {"species": species, "count": len(species)}


# =========================================================================
# GET /api/v1/health/detailed
# =========================================================================
@router.get(
    "/health/detailed",
    summary="Detailed health check",
    description=(
        "Model status and database counts. Requires an elevated role: the payload "
        "exposes model paths, thresholds and gallery size."
    ),
)
async def health_detailed(requester: CurrentUser) -> dict[str, Any]:
    """
    Report detailed model and storage status.

    Restricted to elevated roles because it discloses configured model paths,
    matching thresholds and the size of the identity gallery — useful
    reconnaissance for an attacker and not needed by the mobile client.

    Args:
        requester: Authenticated user record.

    Returns:
        Dict describing model availability, thresholds and storage usage.

    Raises:
        HTTPException 403: Caller lacks an elevated role.
    """
    if requester.get("role") not in ELEVATED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Diagnóstico detallado disponible solo para Researchers y Admins",
        )

    from pathlib import Path

    from app.services.obb_roi_service import get_loaded_obb_roi_service
    from app.services.reid_embedding_service import get_loaded_reid_embedding_service
    from app.services.storage_service import get_disk_usage_mb, get_total_fish_count

    # Report status without forcing a heavyweight model load.
    obb_service = get_loaded_obb_roi_service()
    reid_service = get_loaded_reid_embedding_service()

    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": settings.service_version,
        "match_method": "fishencoder_prototype_topN_vote",
        "obb_model_configured": Path(settings.obb_model_path).is_file(),
        "obb_model_loaded": obb_service is not None and obb_service.is_loaded,
        "reid_model_configured": Path(settings.reid_model_path).is_file(),
        "reid_model_loaded": reid_service is not None and reid_service.is_loaded,
        "reid_model_name": settings.reid_model_name,
        "reid_embedding_dim": settings.reid_embedding_dim,
        "reid_similarity_threshold": settings.reid_similarity_threshold,
        "total_fish_in_database": get_total_fish_count(),
        "disk_usage_mb": get_disk_usage_mb(),
        "nearby_area_radius_km": settings.nearby_area_radius_km,
    }
