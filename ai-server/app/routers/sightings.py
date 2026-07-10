import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header

from app.config import settings
from app.database import get_db_connection
from app.data.czech_species import CZECH_SPECIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sightings", tags=["sightings"])

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

@router.get("/user/{user_id}")
def get_user_sightings(
    user_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve all sightings captured by a specific user from SQLite."""
    _validate_auth(x_fishdex_client_secret, authorization)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM fish_sightings WHERE user_id = ? ORDER BY captured_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        
        sightings_list = []
        for row in rows:
            d = dict(row)
            d["$id"] = d["id"] # Map SQLite 'id' to '$id' for Appwrite models compatibility in client
            sightings_list.append(d)
            
        return sightings_list
    except Exception as e:
        logger.error(f"Failed to fetch user sightings: {e}")
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
