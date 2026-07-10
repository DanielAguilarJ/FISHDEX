"""
FishDex AI Server - Storage Service
=====================================
Hierarchical fish storage system on server disk.
Structure: server-data/{area_code_clean}/{species_slug}/{fish_id}/catch_N/images/ + data.json

IMPORTANT ARCHITECTURAL NOTE:
This service acts as a **local cache for the AI matching pipeline**.
Appwrite is the authoritative source of truth for all fish metadata,
sightings, and user data.  The disk storage here exists solely to:
  1. Cache frame images for embedding comparison (avoids re-downloading)
  2. Store pre-computed embeddings (embeddings.npy) for fast matching

If the disk cache is lost, it can be reconstructed by re-processing
sightings from Appwrite.  The AI server should NEVER be treated as
the canonical store of fish history or metadata.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Base directory for all fish data storage (from config)
BASE_DIR = Path(settings.server_data_dir)


def _ensure_base_dir() -> None:
    """Create the base storage directory if it doesn't exist."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)


def save_catch(
    area_code: str,
    species_slug: str,
    fish_id: str,
    frames: list[np.ndarray],
    metadata: dict,
) -> str:
    """
    Save a fish catch to the hierarchical storage system.

    Creates: server-data/{area_code_clean}/{species_slug}/{fish_id}/catch_{N}/images/ + data.json

    Args:
        area_code: Czech fishing area code (e.g. "401 001" or "401001")
        species_slug: Species slug from czech_species (e.g. "cyprinus_carpio")
        fish_id: Unique fish identifier (e.g. "CZ-401001-CYPCA-0001")
        frames: List of BGR frames as numpy arrays (max 5 saved)
        metadata: Dict with all catch metadata fields

    Returns:
        Path to the created catch folder as string.
    """
    _ensure_base_dir()

    area_code_clean = area_code.replace(" ", "")
    fish_dir = BASE_DIR / area_code_clean / species_slug / fish_id

    # Determine the next catch number
    catch_num = 1
    if fish_dir.exists():
        existing_catches = [
            d for d in fish_dir.iterdir()
            if d.is_dir() and d.name.startswith("catch_")
        ]
        if existing_catches:
            nums = []
            for d in existing_catches:
                try:
                    nums.append(int(d.name.split("_")[1]))
                except (IndexError, ValueError):
                    pass
            if nums:
                catch_num = max(nums) + 1

    catch_dir = fish_dir / f"catch_{catch_num}"
    images_dir = catch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Save frames as JPEG (max 5 frames, quality from config)
    max_save = settings.max_frames_to_save
    frames_to_save = frames[:max_save]
    for i, frame in enumerate(frames_to_save):
        frame_path = images_dir / f"frame_{i}.jpg"
        cv2.imwrite(
            str(frame_path),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality],
        )

    # Add timestamp and catch number to metadata
    metadata_with_extras = {
        **metadata,
        "catch_number": catch_num,
        "images_count": len(frames_to_save),
        "saved_at": datetime.now().isoformat(),
    }

    # Save metadata as data.json
    data_path = catch_dir / "data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(metadata_with_extras, f, ensure_ascii=False, indent=2)

    # Persist embedding for fast future comparisons (avoids re-extraction)
    try:
        from app.services.embedding_service import get_embedding_service
        emb_service = get_embedding_service()
        embedding = emb_service.extract_embeddings(frames_to_save)
        np.save(str(images_dir / "embeddings.npy"), embedding)
    except Exception as emb_exc:
        logger.warning("Failed to save embedding for %s: %s", fish_id, emb_exc)

    logger.info(
        "Saved catch %d for %s → %s (%d frames + embedding)",
        catch_num, fish_id, catch_dir, len(frames_to_save),
    )
    return str(catch_dir)


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
    fish_dir = BASE_DIR / area_code_clean / species_slug / fish_id

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
            except (json.JSONDecodeError, OSError):
                continue

    return history


def check_fish_exists(area_code: str, species_slug: str, fish_id: str) -> bool:
    """
    Check if a fish ID already exists in storage.

    Args:
        area_code: Czech fishing area code
        species_slug: Species slug
        fish_id: Unique fish identifier

    Returns:
        True if the fish directory exists and has at least one catch.
    """
    area_code_clean = area_code.replace(" ", "")
    fish_dir = BASE_DIR / area_code_clean / species_slug / fish_id
    if not fish_dir.exists():
        return False
    # Check it has at least one catch folder
    return any(
        d.is_dir() and d.name.startswith("catch_")
        for d in fish_dir.iterdir()
    )


def list_fish_in_area(area_code: str, species_slug: Optional[str] = None) -> list[str]:
    """
    List all Fish IDs in an area, optionally filtered by species.

    Args:
        area_code: Czech fishing area code
        species_slug: Optional species filter

    Returns:
        List of Fish ID strings found in the area.
    """
    area_code_clean = area_code.replace(" ", "")
    area_dir = BASE_DIR / area_code_clean

    if not area_dir.exists():
        return []

    fish_ids = []
    if species_slug:
        species_dir = area_dir / species_slug
        if species_dir.exists():
            for fish_dir in species_dir.iterdir():
                if fish_dir.is_dir():
                    fish_ids.append(fish_dir.name)
    else:
        for species_dir in area_dir.iterdir():
            if species_dir.is_dir():
                for fish_dir in species_dir.iterdir():
                    if fish_dir.is_dir():
                        fish_ids.append(fish_dir.name)

    return sorted(fish_ids)


def get_restricted_history(history: list[dict]) -> list[dict]:
    """
    Return history with GPS coordinates removed (for fisherman role).
    Researchers get full history; fishermen get restricted version.

    Args:
        history: Full catch history list

    Returns:
        History with latitude/longitude fields removed or masked.
    """
    restricted = []
    for catch in history:
        catch_copy = {**catch}
        # Remove exact GPS coordinates
        catch_copy.pop("latitude", None)
        catch_copy.pop("longitude", None)
        catch_copy.pop("location_lat", None)
        catch_copy.pop("location_lon", None)
        # Keep area_code (general location is OK)
        restricted.append(catch_copy)
    return restricted


def generate_fish_id(area_code: str, species_slug: str) -> str:
    """
    Generate a unique fish ID for a new fish.

    Format: CZ-{area_code_clean}-{FIRST3GENUS+FIRST2SPECIES}-{sequential_4digit}
    Example: CZ-401001-CYPCA-0042

    Args:
        area_code: Czech fishing area code
        species_slug: Species slug (e.g. "cyprinus_carpio")

    Returns:
        A unique fish ID string.
    """
    area_code_clean = area_code.replace(" ", "")

    # Generate species abbreviation: first 3 chars of genus + first 2 chars of species
    parts = species_slug.split("_")
    if len(parts) >= 2:
        abbrev = (parts[0][:3] + parts[1][:2]).upper()
    else:
        abbrev = species_slug[:5].upper()

    # Find the next sequential number
    species_dir = BASE_DIR / area_code_clean / species_slug
    next_num = 1

    if species_dir.exists():
        existing_nums = []
        pattern = re.compile(r"CZ-\w+-\w+-(\d+)")
        for fish_dir in species_dir.iterdir():
            if fish_dir.is_dir():
                match = pattern.match(fish_dir.name)
                if match:
                    try:
                        existing_nums.append(int(match.group(1)))
                    except ValueError:
                        pass
        if existing_nums:
            next_num = max(existing_nums) + 1

    return f"CZ-{area_code_clean}-{abbrev}-{next_num:04d}"


def get_species_in_area(area_code: str) -> list[str]:
    """
    Get list of unique species slugs found in an area's storage.

    Args:
        area_code: Czech fishing area code

    Returns:
        List of species slug strings.
    """
    area_code_clean = area_code.replace(" ", "")
    area_dir = BASE_DIR / area_code_clean

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


def load_fish_frames(
    area_code: str,
    species_slug: str,
    fish_id: str,
    catch_number: Optional[int] = None,
) -> list[np.ndarray]:
    """
    Load stored JPEG frames for a specific fish (from latest catch or a specific one).

    Args:
        area_code:    Czech fishing area code.
        species_slug: Species slug.
        fish_id:      Unique fish identifier.
        catch_number: If provided, load from that specific catch. Otherwise, load from latest.

    Returns:
        List of BGR numpy arrays, one per stored frame.
    """
    area_code_clean = area_code.replace(" ", "")
    fish_dir = BASE_DIR / area_code_clean / species_slug / fish_id

    if not fish_dir.exists():
        return []

    if catch_number is not None:
        images_dir = fish_dir / f"catch_{catch_number}" / "images"
    else:
        # Find the latest catch directory
        catch_dirs = sorted(
            [d for d in fish_dir.iterdir() if d.is_dir() and d.name.startswith("catch_")],
            key=lambda d: d.name,
        )
        if not catch_dirs:
            return []
        images_dir = catch_dirs[-1] / "images"

    if not images_dir.is_dir():
        return []

    frames: list[np.ndarray] = []
    for img_path in sorted(images_dir.glob("frame_*.jpg")):
        img = cv2.imread(str(img_path))
        if img is not None:
            frames.append(img)

    return frames


def get_area_stats(area_code: str) -> dict:
    """
    Compute statistics for a fishing area's stored data.

    Args:
        area_code: Czech fishing area code.

    Returns:
        Dict with total_fish, species_breakdown, most_recent_catch, total_catches.
    """
    area_code_clean = area_code.replace(" ", "")
    area_dir = BASE_DIR / area_code_clean

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
                    except (json.JSONDecodeError, OSError):
                        pass

        stats["species_breakdown"][species_slug] = fish_count
        stats["total_fish"] += fish_count

    stats["most_recent_catch"] = latest_datetime
    return stats


def get_fish_history_by_id(fish_id: str) -> Optional[dict]:
    """
    Search across ALL areas and species for a fish_id and return its full history.

    This is an O(areas × species) scan, but necessary when only the fish_id is known.

    Args:
        fish_id: The unique fish identifier (e.g. "CZ-401001-CYPCA-0001").

    Returns:
        Dict with area_code, species_slug, fish_id, history list, or None if not found.
    """
    if not BASE_DIR.exists():
        return None

    for area_dir in BASE_DIR.iterdir():
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
    if not BASE_DIR.exists():
        return 0

    count = 0
    for area_dir in BASE_DIR.iterdir():
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
    if not BASE_DIR.exists():
        return 0.0

    total_bytes = 0
    for root, _dirs, files in os.walk(BASE_DIR):
        for f in files:
            try:
                total_bytes += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass

    return round(total_bytes / (1024 * 1024), 2)
