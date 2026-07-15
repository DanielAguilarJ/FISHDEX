import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query

from app.config import settings
from app.database import get_db_connection
from app.data.czech_species import CZECH_SPECIES
from app.routers.auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sightings", tags=["sightings"])

_ELEVATED_ROLES = {"researcher", "admin"}


def _get_authenticated_user(authorization: Optional[str]) -> dict:
    """Resolve the local session token and load the authoritative database role."""
    user_id = get_current_user_id(authorization)

    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=401, detail="Usuario autenticado no encontrado")

    return dict(row)


def _serialize_sighting(row) -> dict:
    sighting = dict(row)
    sighting["$id"] = sighting["id"]
    return sighting


def _has_elevated_access(user: dict) -> bool:
    return user.get("role") in _ELEVATED_ROLES

def _validate_auth(
    x_fishdex_client_secret: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    """Validate request authentication."""
    if settings.skip_auth:
        return

    expected_secret = settings.client_secret
    if x_fishdex_client_secret and x_fishdex_client_secret == expected_secret:
        return

    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == expected_secret:
            return

    raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/map")
def get_map_sightings(
    limit: int = Query(default=500, ge=1, le=1000),
    authorization: Optional[str] = Header(default=None),
):
    """Return geolocated sightings visible to the authenticated user's role."""
    requester = _get_authenticated_user(authorization)

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
    query = f"""
        SELECT * FROM fish_sightings
        WHERE {' AND '.join(filters)}
        ORDER BY captured_at DESC
        LIMIT ?
    """

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [_serialize_sighting(row) for row in rows]
    except Exception as e:
        logger.error("Failed to fetch map sightings: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al recuperar capturas del mapa")
    finally:
        conn.close()


@router.get("/fish/{fish_id}/history")
def get_fish_history(
    fish_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """Return the complete chronological history of one fish to researchers/admins."""
    requester = _get_authenticated_user(authorization)
    if not _has_elevated_access(requester):
        raise HTTPException(
            status_code=403,
            detail="El historial completo está disponible solo para Researchers y Admins",
        )

    conn = get_db_connection()
    try:
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
        return [_serialize_sighting(row) for row in rows]
    except Exception as e:
        logger.error("Failed to fetch history for fish %s: %s", fish_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al recuperar el historial del pez")
    finally:
        conn.close()


@router.get("/user/{user_id}")
def get_user_sightings(
    user_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve sightings for the owner or an authenticated researcher/admin."""
    requester = _get_authenticated_user(authorization)
    if requester["id"] != user_id and not _has_elevated_access(requester):
        raise HTTPException(status_code=403, detail="No puedes consultar capturas de otro usuario")

    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM fish_sightings
            WHERE user_id = ?
            ORDER BY captured_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()
        return [_serialize_sighting(row) for row in rows]
    except Exception as e:
        logger.error("Failed to fetch user sightings: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al recuperar avistamientos")
    finally:
        conn.close()

@router.get("/individuals")
def get_fish_individuals(
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve all unique matched fish individuals."""
    _validate_auth(x_fishdex_client_secret, authorization)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM fish_individuals ORDER BY last_seen_at DESC")
        rows = cursor.fetchall()
        
        individuals_list = []
        for row in rows:
            d = dict(row)
            d["$id"] = d["id"] # Map SQLite 'id' to '$id'
            individuals_list.append(d)
            
        return individuals_list
    except Exception as e:
        logger.error(f"Failed to fetch fish individuals: {e}")
        raise HTTPException(status_code=500, detail="Error al recuperar individuos de peces")
    finally:
        conn.close()

@router.get("/stats/{user_id}")
def get_user_stats(
    user_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve XP stats and counts for a user."""
    _validate_auth(x_fishdex_client_secret, authorization)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            # Return initial/default empty stats
            return {
                "user_id": user_id,
                "total_xp": 0,
                "total_sightings": 0,
                "total_species": 0,
                "level": 1
            }
            
        d = dict(row)
        d["$id"] = d["id"] # Map SQLite 'id' to '$id'
        # Compute level dynamically based on XP (e.g. 100 XP per level)
        d["level"] = (d["total_xp"] // 100) + 1
        return d
    except Exception as e:
        logger.error(f"Failed to fetch user stats: {e}")
        raise HTTPException(status_code=500, detail="Error al recuperar estadísticas de usuario")
    finally:
        conn.close()

@router.get("/catalog")
def get_species_catalog():
    """Retrieve the static Czech species catalog list."""
    return CZECH_SPECIES
