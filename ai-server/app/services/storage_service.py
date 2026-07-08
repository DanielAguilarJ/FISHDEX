"""
FishDex AI Server - Storage Service
=====================================
Hierarchical fish storage system on server disk.
Structure: server-data/{area_code_clean}/{species_slug}/{fish_id}/catch_N/images/ + data.json
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Base directory for all fish data storage
BASE_DIR = Path("server-data")


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

    # Save frames as JPEG (max 5 frames, quality 90)
    frames_to_save = frames[:5]
    for i, frame in enumerate(frames_to_save):
        frame_path = images_dir / f"frame_{i}.jpg"
        cv2.imwrite(
            str(frame_path),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 90],
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

    Format: CZ-{area_code_clean}-{FIRST5_LATIN_UPPER}-{sequential_4digit}
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
