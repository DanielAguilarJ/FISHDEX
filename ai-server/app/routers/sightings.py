"""
FishDex AI Server - Sighting queries
====================================
Read-only endpoints for the mobile app and the research dashboard.

Authorisation model
-------------------
Every endpoint that returns per-user or per-fish data requires a **signed
session token** and resolves the caller's role from the database. The shared
client secret is never sufficient on its own, because it identifies the
application (every install ships the same value), not a user.

Location privacy: precise GPS coordinates of individual fish are only exposed to
``researcher`` and ``admin`` roles. Fishermen see their own captures only.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.data.czech_species import CZECH_SPECIES
from app.database import db_session
from app.routers.auth import ELEVATED_ROLES, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sightings", tags=["sightings"])

# Columns that reveal a fish's precise location or another user's identity.
_SENSITIVE_INDIVIDUAL_KEYS = (
    "last_seen_lat",
    "last_seen_lng",
    "first_seen_lat",
    "first_seen_lng",
    "first_seen_by",
    "last_seen_by",
)


def _serialize_sighting(row: sqlite3.Row) -> dict[str, Any]:
    """
    Convert a sighting row to the JSON shape the Flutter client expects.

    Args:
        row: Row from ``fish_sightings``.

    Returns:
        Dict with an added ``$id`` alias for the primary key.
    """
    sighting = dict(row)
    sighting["$id"] = sighting["id"]
    return sighting


def _has_elevated_access(user: dict[str, Any]) -> bool:
    """
    Report whether the user may see other people's data and precise GPS.

    Args:
        user: Authenticated user record.

    Returns:
        True for ``researcher`` and ``admin``.
    """
    return user.get("role") in ELEVATED_ROLES


def _strip_individual_location(individual: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of a fish individual without location or attribution fields.

    Args:
        individual: Row from ``fish_individuals`` as a dict.

    Returns:
        A new dict with sensitive keys removed (the input is not mutated).
    """
    return {k: v for k, v in individual.items() if k not in _SENSITIVE_INDIVIDUAL_KEYS}


CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/map")
def get_map_sightings(
    requester: CurrentUser,
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """
    Return geolocated sightings visible to the authenticated user's role.

    Fishermen receive only their own captures; researchers and admins receive
    all captures.

    Args:
        requester: Authenticated user record.
        limit: Maximum number of rows to return.

    Returns:
        List of serialized sightings ordered by capture time descending.

    Raises:
        HTTPException 500: Query failure.
    """
    filters = [
        "location_lat IS NOT NULL",
        "location_lng IS NOT NULL",
        "location_lat BETWEEN -90 AND 90",
        "location_lng BETWEEN -180 AND 180",
    ]
    params: list[object] = []

    if not _has_elevated_access(requester):
        filters.append("user_id = ?")
        params.append(requester["id"])

    params.append(limit)
    # The WHERE clause is assembled from the fixed literals above only; no
    # user-controlled string ever reaches the SQL text.
    # `filters` holds only the fixed literals declared above; the caller's id and
    # limit travel as bound parameters. Ruff cannot prove that, hence the noqa.
    query = (
        "SELECT * FROM fish_sightings "  # noqa: S608
        f"WHERE {' AND '.join(filters)} "
        "ORDER BY captured_at DESC LIMIT ?"
    )

    try:
        with db_session() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        logger.error("Failed to fetch map sightings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar capturas del mapa",
        ) from exc
    return [_serialize_sighting(row) for row in rows]


@router.get("/fish/{fish_id}/history")
def get_fish_history(
    fish_id: str,
    requester: CurrentUser,
) -> list[dict[str, Any]]:
    """
    Return the complete chronological history of one fish.

    Restricted to researchers and admins because the history discloses the
    precise recapture locations of an individual animal.

    Args:
        fish_id: Fish identifier, e.g. ``CZ-401001-CYPCA-0001``.
        requester: Authenticated user record.

    Returns:
        Sightings ordered chronologically.

    Raises:
        HTTPException 403: Caller lacks an elevated role.
        HTTPException 500: Query failure.
    """
    if not _has_elevated_access(requester):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El historial completo está disponible solo para Researchers y Admins",
        )

    try:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fish_sightings
                WHERE fish_id = ?
                  AND location_lat IS NOT NULL
                  AND location_lng IS NOT NULL
                  AND location_lat BETWEEN -90 AND 90
                  AND location_lng BETWEEN -180 AND 180
                ORDER BY captured_at ASC, catch_number ASC
                """,
                (fish_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error(
            "Failed to fetch history for fish %s: %s", fish_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar el historial del pez",
        ) from exc
    return [_serialize_sighting(row) for row in rows]


@router.get("/user/{user_id}")
def get_user_sightings(
    user_id: str,
    requester: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """
    Retrieve sightings for the owner or an authenticated researcher/admin.

    Args:
        user_id: Owner of the requested sightings.
        requester: Authenticated user record.
        limit: Page size.
        offset: Page offset.

    Returns:
        List of serialized sightings.

    Raises:
        HTTPException 403: Caller is neither the owner nor elevated.
        HTTPException 500: Query failure.
    """
    if requester["id"] != user_id and not _has_elevated_access(requester):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes consultar capturas de otro usuario",
        )

    try:
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fish_sightings
                WHERE user_id = ?
                ORDER BY captured_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("Failed to fetch user sightings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar avistamientos",
        ) from exc
    return [_serialize_sighting(row) for row in rows]


@router.get("/individuals")
def get_fish_individuals(
    requester: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """
    Retrieve catalogued fish individuals.

    Location and attribution columns are stripped for non-elevated callers, who
    previously received the first/last GPS position of every catalogued fish.

    Args:
        requester: Authenticated user record.
        limit: Page size.
        offset: Page offset.

    Returns:
        List of fish individuals, location-redacted unless the caller is
        a researcher or admin.

    Raises:
        HTTPException 500: Query failure.
    """
    try:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT * FROM fish_individuals ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    except sqlite3.Error as exc:
        logger.error("Failed to fetch fish individuals: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar individuos de peces",
        ) from exc

    elevated = _has_elevated_access(requester)
    individuals: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["$id"] = record["id"]
        individuals.append(record if elevated else _strip_individual_location(record))
    return individuals


@router.get("/stats/{user_id}")
def get_user_stats(
    user_id: str,
    requester: CurrentUser,
) -> dict[str, Any]:
    """
    Retrieve XP stats and counts for a user.

    Args:
        user_id: Owner of the requested statistics.
        requester: Authenticated user record.

    Returns:
        Stats row augmented with a derived ``level``, or a zeroed record when the
        user has no stats yet.

    Raises:
        HTTPException 403: Caller is neither the owner nor elevated.
        HTTPException 500: Query failure.
    """
    if requester["id"] != user_id and not _has_elevated_access(requester):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes consultar estadísticas de otro usuario",
        )

    try:
        with db_session() as conn:
            row = conn.execute(
                "SELECT * FROM user_stats WHERE user_id = ?", (user_id,)
            ).fetchone()
    except sqlite3.Error as exc:
        logger.error("Failed to fetch user stats: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar estadísticas de usuario",
        ) from exc

    if row is None:
        return {
            "user_id": user_id,
            "total_xp": 0,
            "total_sightings": 0,
            "total_species": 0,
            "level": 1,
        }

    stats = dict(row)
    stats["$id"] = stats["id"]
    stats["level"] = (stats.get("total_xp") or 0) // 100 + 1
    return stats


@router.get("/catalog")
def get_species_catalog() -> list[dict[str, Any]]:
    """
    Retrieve the static Czech species catalog.

    Public: the catalog is reference data with no user or location content.

    Returns:
        The full species list.
    """
    return CZECH_SPECIES
