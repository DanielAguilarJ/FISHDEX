"""
FishDex AI Server - Subset Service
=====================================
Step 3 of the pipeline: given an area code and species,
build the comparison subset of existing fish profiles
by scanning server-data/ for the primary area and nearby areas.
"""

import logging
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _load_fish_profiles_from_dir(species_dir: Path) -> list[dict]:
    """
    Scan a species directory and return profile dicts for every fish found.

    Args:
        species_dir: Path like server-data/401001/cyprinus_carpio/

    Returns:
        List of dicts, each with fish_id, fish_dir, catches_count, latest_images_dir.
    """
    profiles: list[dict] = []
    if not species_dir.is_dir():
        return profiles

    for fish_dir in sorted(species_dir.iterdir()):
        if not fish_dir.is_dir():
            continue

        # Count catch_N folders
        catch_dirs = sorted(
            [d for d in fish_dir.iterdir() if d.is_dir() and d.name.startswith("catch_")],
            key=lambda d: d.name,
        )
        if not catch_dirs:
            continue

        latest_images = catch_dirs[-1] / "images"

        # Collect ALL image directories across catches for multi-catch prototype building.
        # The similarity service samples up to reid_max_support_images_per_identity
        # rows from the pooled embedding matrix, so having more dirs is better.
        image_dirs = [
            catch_dir / "images"
            for catch_dir in catch_dirs
            if (catch_dir / "images").is_dir()
        ]

        profiles.append(
            {
                "fish_id": fish_dir.name,
                "fish_dir": fish_dir,
                "catches_count": len(catch_dirs),
                "latest_images_dir": latest_images if latest_images.is_dir() else catch_dirs[-1],
                "image_dirs": image_dirs,
            }
        )

    return profiles


def get_comparison_subset(
    area_code: str,
    species_slug: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> list[dict]:
    """
    Build the comparison subset of existing fish profiles.

    Strategy:
      1. Load all fish from server-data/{area_code_clean}/{species_slug}/
      2. If GPS coords provided, find nearby areas within configured radius
      3. For each nearby area, also load fish of the same species
      4. Return combined list, deduplicated by fish_id

    Args:
        area_code:    Czech fishing area code (e.g. '401 001')
        species_slug: Species slug (e.g. 'cyprinus_carpio')
        latitude:     GPS latitude of the catch (optional)
        longitude:    GPS longitude of the catch (optional)

    Returns:
        List of fish profile dicts ready for similarity comparison.
    """
    base_dir = Path(settings.server_data_dir)
    area_clean = area_code.replace(" ", "")
    subset: list[dict] = []
    seen_ids: set[str] = set()

    # --- Primary area ---
    primary_species_dir = base_dir / area_clean / species_slug
    for profile in _load_fish_profiles_from_dir(primary_species_dir):
        if profile["fish_id"] not in seen_ids:
            seen_ids.add(profile["fish_id"])
            subset.append(profile)

    # --- Nearby areas (within configured radius) ---
    if latitude is not None and longitude is not None:
        try:
            from app.data.czech_areas import find_nearest_areas

            nearby = find_nearest_areas(
                latitude, longitude, max_distance_km=settings.nearby_area_radius_km
            )
            for area in nearby:
                nearby_clean = area["code_clean"]
                if nearby_clean == area_clean:
                    continue  # already loaded
                nearby_species_dir = base_dir / nearby_clean / species_slug
                for profile in _load_fish_profiles_from_dir(nearby_species_dir):
                    if profile["fish_id"] not in seen_ids:
                        seen_ids.add(profile["fish_id"])
                        subset.append(profile)
        except Exception as exc:
            logger.warning("Could not load nearby areas: %s", exc)

    logger.info(
        "Subset for area=%s species=%s: %d fish profiles (searched %s nearby areas)",
        area_code,
        species_slug,
        len(subset),
        "with" if (latitude and longitude) else "without",
    )
    return subset
