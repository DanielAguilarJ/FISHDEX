"""
FishDex AI Server - Storage Service
=====================================
Hierarchical fish storage system on server disk.
Structure: server-data/{area_code_clean}/{species_slug}/{fish_id}/catch_N/images/ + data.json

This service manages the local storage for the AI matching pipeline.
The SQLite database is the authoritative source of truth for all fish
metadata, sightings, and user data. The disk storage here exists to:
  1. Cache frame images for embedding comparison
  2. Store pre-computed embeddings for fast matching
  3. Preserve raw video and crop artifacts for audit/rebuild

If the disk cache is lost, it can be reconstructed by re-processing
from the database using rebuild_embeddings.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional


from app.config import settings

logger = logging.getLogger(__name__)


def base_dir() -> Path:
    """
    Resolve the storage root from the current configuration.

    Read on every call rather than captured at import time. A module-level
    ``base_dir() = Path(settings.server_data_dir)`` froze the path at first import,
    so any later change to the setting — a test fixture, or a deployment that
    reconfigures the data directory — was silently ignored while the module kept
    reading the original location.

    Returns:
        The configured storage root.
    """
    return Path(settings.server_data_dir)


def _ensure_base_dir() -> None:
    """Create the base storage directory if it doesn't exist."""
    base_dir().mkdir(parents=True, exist_ok=True)


def get_species_in_area(area_code: str) -> list[str]:
    """
    Get list of unique species slugs found in an area's storage.

    Args:
        area_code: Czech fishing area code

    Returns:
        List of species slug strings.
    """
    area_code_clean = area_code.replace(" ", "")
    area_dir = base_dir() / area_code_clean

    if not area_dir.exists():
        return []

    species = []
    for species_dir in area_dir.iterdir():
        if species_dir.is_dir() and not species_dir.name.startswith("."):
            species.append(species_dir.name)

    return sorted(species)


# =========================================================================
# NEW: Functions added for the full pipeline
# =========================================================================


def get_area_stats(area_code: str) -> dict:
    """
    Compute statistics for a fishing area's stored data.

    Args:
        area_code: Czech fishing area code.

    Returns:
        Dict with total_fish, species_breakdown, most_recent_catch, total_catches.
    """
    area_code_clean = area_code.replace(" ", "")
    area_dir = base_dir() / area_code_clean

    stats: dict = {
        "area_code": area_code,
        "total_fish": 0,
        "total_catches": 0,
        "species_breakdown": {},
        "most_recent_catch": None,
    }

    if not area_dir.exists():
        return stats

    latest_datetime: Optional[str] = None

    for species_dir in area_dir.iterdir():
        if not species_dir.is_dir() or species_dir.name.startswith("."):
            continue

        species_slug = species_dir.name
        fish_count = 0

        for fish_dir in species_dir.iterdir():
            if not fish_dir.is_dir():
                continue
            fish_count += 1

            for catch_dir in fish_dir.iterdir():
                if not catch_dir.is_dir() or not catch_dir.name.startswith("catch_"):
                    continue
                stats["total_catches"] += 1

                data_path = catch_dir / "data.json"
                if data_path.exists():
                    try:
                        with open(data_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        dt = data.get("saved_at") or data.get("datetime")
                        if dt and (latest_datetime is None or dt > latest_datetime):
                            latest_datetime = dt
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.warning(
                            "Skipping unreadable catch record %s: %s", data_path, exc
                        )

        stats["species_breakdown"][species_slug] = fish_count
        stats["total_fish"] += fish_count

    stats["most_recent_catch"] = latest_datetime
    return stats


def get_fish_history(area_code: str, species_slug: str, fish_id: str) -> list[dict]:
    """
    Get the complete catch history for a specific fish.

    Args:
        area_code: Czech fishing area code
        species_slug: Species slug
        fish_id: Unique fish identifier

    Returns:
        List of all data.json contents from all catch_X folders,
        sorted by catch number. Each dict includes "images_count" field.
    """
    area_code_clean = area_code.replace(" ", "")
    fish_dir = base_dir() / area_code_clean / species_slug / fish_id

    if not fish_dir.exists():
        return []

    history = []
    for catch_dir in sorted(fish_dir.iterdir()):
        if not catch_dir.is_dir() or not catch_dir.name.startswith("catch_"):
            continue
        data_path = catch_dir / "data.json"
        if data_path.exists():
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Ensure images_count is present
                if "images_count" not in data:
                    images_dir = catch_dir / "images"
                    if images_dir.exists():
                        data["images_count"] = len(list(images_dir.glob("*.jpg")))
                    else:
                        data["images_count"] = 0
                history.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping unreadable catch record %s: %s", data_path, exc)
                continue

    return history


def get_fish_history_by_id(fish_id: str) -> Optional[dict]:
    """
    Search across ALL areas and species for a fish_id and return its full history.

    This is an O(areas × species) scan, but necessary when only the fish_id is known.

    Args:
        fish_id: The unique fish identifier (e.g. "CZ-401001-CYPCA-0001").

    Returns:
        Dict with area_code, species_slug, fish_id, history list, or None if not found.
    """
    if not base_dir().exists():
        return None

    for area_dir in base_dir().iterdir():
        if not area_dir.is_dir():
            continue
        for species_dir in area_dir.iterdir():
            if not species_dir.is_dir():
                continue
            fish_dir = species_dir / fish_id
            if fish_dir.is_dir():
                # Found it — load history
                history = get_fish_history(area_dir.name, species_dir.name, fish_id)
                return {
                    "area_code": area_dir.name,
                    "species_slug": species_dir.name,
                    "fish_id": fish_id,
                    "history": history,
                    "total_catches": len(history),
                }

    return None


def get_total_fish_count() -> int:
    """
    Count total number of unique fish across all areas and species.

    Returns:
        Total fish count.
    """
    if not base_dir().exists():
        return 0

    count = 0
    for area_dir in base_dir().iterdir():
        if not area_dir.is_dir():
            continue
        for species_dir in area_dir.iterdir():
            if not species_dir.is_dir():
                continue
            for fish_dir in species_dir.iterdir():
                if fish_dir.is_dir():
                    count += 1
    return count


def get_disk_usage_mb() -> float:
    """
    Calculate total disk usage of server-data/ in megabytes.

    Returns:
        Disk usage in MB.
    """
    if not base_dir().exists():
        return 0.0

    total_bytes = 0
    for root, _dirs, files in os.walk(base_dir()):
        for f in files:
            try:
                total_bytes += os.path.getsize(os.path.join(root, f))
            except OSError as exc:
                # A file removed mid-walk is normal; log at debug to avoid noise.
                logger.debug("Skipping %s while sizing storage: %s", f, exc)

    return round(total_bytes / (1024 * 1024), 2)
