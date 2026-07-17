"""
FishDex AI Server - Inference Service (Real Pipeline)
======================================================
Implements the full 7-step identification pipeline:
  0. Receive cropped frames
  1. Resolve species info
  2. (Crop already done by caller)
  3. Build comparison subset from local embedding cache
  4. Similarity scoring against existing fish profiles
  5. Decision: new fish vs recapture
  6. Save to local cache (frames + embeddings for future comparisons)
  7. Build role-based response

IMPORTANT: This service proposes a fish_id. Appwrite's `match-fish-id`
function is the authoritative confirmation step.  The local disk storage
is a cache for the similarity pipeline, NOT the source of truth.
"""

import logging
import random
import time
from datetime import datetime
from typing import Optional

import numpy as np

from app.config import settings
from app.models.schemas import FishPreviousData

logger = logging.getLogger(__name__)

# XP values by species rarity
XP_BY_RARITY = {
    "common": 10,
    "uncommon": 25,
    "rare": 50,
    "legendary": 100,
}
XP_NEW_FISH_BONUS = 50


# =============================================================================
# PLACEHOLDER MODEL (ultimate fallback)
# =============================================================================
class PlaceholderModel:
    """
    Legacy placeholder that generates random identifications.
    Only used if both SubsetService and SimilarityService fail.
    """

    def __init__(self) -> None:
        """Initialize placeholder model."""
        self.is_loaded = True

    def random_decision(self) -> bool:
        """Return True if should be treated as new fish (50/50)."""
        return random.random() < 0.5


# =============================================================================
# INFERENCE SERVICE — Real 7-step pipeline
# =============================================================================
class InferenceService:
    """Orchestrates the full fish identification pipeline."""

    def __init__(self) -> None:
        """Initialize inference service with placeholder fallback."""
        self._placeholder = PlaceholderModel()
        logger.info("InferenceService initialized")

    def identify_fish(
        self,
        cropped_frames: list[np.ndarray],
        area_code: str = "",
        species: Optional[str] = None,
        user_role: str = "fisherman",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Run the full 7-step identification pipeline.

        Args:
            cropped_frames: List of cropped BGR frames (Step 2 output, typically 5).
            area_code:      Czech fishing area code (e.g. '401 001').
            species:        Species name if already known (skip Step 1 classification).
            user_role:      'fisherman' or 'researcher'.
            metadata:       Dict with all catch metadata fields from the form.

        Returns:
            Dict with all fields needed for IdentifyResponse.
        """
        t_start = time.perf_counter()
        if metadata is None:
            metadata = {}

        # ─── Step 1: Resolve species info ────────────────────────────
        t1 = time.perf_counter()
        species_info = None
        species_name = "Unknown Species"
        scientific_name: Optional[str] = None
        species_slug = "species_unknown"
        species_czech: Optional[str] = None
        rarity = "common"
        xp_base = 10
        family: Optional[str] = None

        if species:
            try:
                from app.data.czech_species import find_species_by_name
                species_info = find_species_by_name(species)
            except Exception:
                pass

        if species_info:
            species_name = species_info["english_name"]
            scientific_name = species_info["latin_name"]
            species_slug = species_info["slug"]
            species_czech = species_info["czech_name"]
            rarity = species_info["rarity"]
            xp_base = species_info["xp_base"]
        elif species:
            # User provided a name we don't recognise — use it anyway
            species_name = species
            species_slug = species.lower().replace(" ", "_")

        logger.info("[Step 1] Species resolved: %s (%s) in %.1fms",
                     species_name, species_slug, (time.perf_counter() - t1) * 1000)

        # ─── Step 2: Area lookup ─────────────────────────────────────
        area_info = None
        if area_code:
            try:
                from app.data.czech_areas import find_area_by_code
                area_info = find_area_by_code(area_code)
            except Exception:
                pass

        # ─── Step 3: Build comparison subset ─────────────────────────
        t3 = time.perf_counter()
        subset: list[dict] = []
        if area_code and species_slug != "species_unknown":
            try:
                from app.services.subset_service import get_comparison_subset
                subset = get_comparison_subset(
                    area_code=area_code,
                    species_slug=species_slug,
                    latitude=metadata.get("latitude"),
                    longitude=metadata.get("longitude"),
                )
            except Exception as exc:
                logger.warning("[Step 3] Subset service error: %s", exc)

        logger.info("[Step 3] Subset built: %d candidates in %.1fms",
                     len(subset), (time.perf_counter() - t3) * 1000)

        # ─── Step 4: Similarity scoring ──────────────────────────────
        t4 = time.perf_counter()
        matched_fish_id: Optional[str] = None
        similarity_score: float = 0.0
        match_margin_val: float = 0.0

        if subset and cropped_frames:
            try:
                from app.services.similarity_service import get_similarity_service
                sim_service = get_similarity_service()
                match_result = sim_service.find_best_match(
                    new_frames=cropped_frames,
                    subset=subset,
                    threshold=settings.reid_similarity_threshold,
                )
                matched_fish_id = match_result.fish_id
                similarity_score = match_result.score
                match_margin_val = match_result.margin
            except Exception as exc:
                logger.warning("[Step 4] Similarity service error: %s", exc)

        logger.info("[Step 4] Similarity done: best_match=%s score=%.4f in %.1fms",
                     matched_fish_id, similarity_score, (time.perf_counter() - t4) * 1000)

        # Capture voting details for response (if similarity service ran)
        _match_result = locals().get("match_result")

        # ─── Step 5: Decision (new fish vs recapture) ────────────────
        is_new = True
        fish_id = ""
        catch_number = 1
        history: list[dict] = []

        if area_code and species_slug:
            try:
                from app.services.storage_service import (
                    generate_fish_id,
                    save_catch,
                    get_fish_history,
                )

                if matched_fish_id is not None:
                    # ── RECAPTURE ──
                    fish_id = matched_fish_id
                    is_new = False
                    logger.info("[Step 5] RECAPTURE — fish_id=%s (score=%.4f)",
                                fish_id, similarity_score)
                else:
                    # ── NEW FISH ──
                    fish_id = generate_fish_id(area_code, species_slug)
                    is_new = True
                    logger.info("[Step 5] NEW FISH — fish_id=%s", fish_id)

                # ─── Step 6: Save catch ──────────────────────────────
                storage_metadata = {
                    "area_code": area_code,
                    "fisherman_id": metadata.get("fisherman_id", ""),
                    "datetime": datetime.now().isoformat(),
                    "latitude": metadata.get("latitude"),
                    "longitude": metadata.get("longitude"),
                    "species": species_name,
                    "species_slug": species_slug,
                    "species_czech": species_czech,
                    "species_latin": scientific_name,
                    "fish_state": metadata.get("fish_state"),
                    "name": metadata.get("name"),
                    "weather": metadata.get("weather"),
                    "bite": metadata.get("bite"),
                    "size": metadata.get("size"),
                    "user_role": user_role,
                }

                save_catch(area_code, species_slug, fish_id, cropped_frames, storage_metadata)

                # Reload history after save
                history = get_fish_history(area_code, species_slug, fish_id)
                catch_number = len(history)

            except Exception as exc:
                logger.error("[Step 5-6] Storage error: %s", exc, exc_info=True)
                if not fish_id:
                    fish_id = f"CZ-{area_code.replace(' ', '')}-TEMP-{random.randint(1000, 9999)}"
        else:
            # No area code — generate a simple fallback ID
            fish_id = f"FISH-{random.randint(1000, 9999)}"

        # ─── Step 7: Build response ──────────────────────────────────
        # detection_confidence: real average OBB confidence from ROI extraction.
        # For new fish, confidence = 0.0 (no prior reference to compare against).
        # For recaptures, confidence = the raw similarity score.
        roi_confidences = metadata.get("_roi_confidences") or []
        if roi_confidences:
            detection_confidence = float(sum(roi_confidences) / len(roi_confidences))
        else:
            detection_confidence = 0.0
        match_confidence = similarity_score  # raw value from similarity service
        confidence = similarity_score if not is_new else 0.0
        xp_earned = xp_base + (XP_NEW_FISH_BONUS if is_new else 0)

        # Recaptura ambígua: score apenas supera el umbral o margen pequeño.
        # Permite que el usuario confirme antes de guardar como verdadera recaptura.
        _ambiguous_band = settings.reid_similarity_threshold + 0.05
        _min_margin = getattr(settings, "reid_min_margin", 0.05)
        ambiguous_recapture = (
            not is_new
            and (similarity_score < _ambiguous_band or match_margin_val < _min_margin * 2)
        )
        estimated_size = metadata.get("size") or 0.0

        # Build previous data if recapture
        previous_data = None
        if not is_new and history and len(history) > 1:
            first_catch = history[0]
            last_catch = history[-2]  # second-to-last is the previous one
            prev_size = last_catch.get("size")
            previous_data = FishPreviousData(
                fish_id=fish_id,
                species=species_name,
                first_seen_date=first_catch.get("datetime", ""),
                first_seen_location=first_catch.get("area_code", ""),
                total_sightings=len(history),
                last_seen_date=last_catch.get("datetime", ""),
                last_estimated_size_cm=round(float(prev_size), 1) if prev_size else 0.0,
                growth_cm=round(float(estimated_size) - float(prev_size), 1) if (prev_size and estimated_size) else 0.0,
            )

        # Role-based history filtering
        full_history: Optional[list] = None
        if user_role == "researcher" and history:
            full_history = history
        elif user_role == "fisherman" and history:
            try:
                from app.services.storage_service import get_restricted_history
                full_history = get_restricted_history(history)
            except Exception:
                full_history = None

        # Message
        if is_new:
            message = f"NEW FISH DISCOVERED! You identified a {species_name} for the first time."
        else:
            message = f"RECAPTURE! This {species_name} has been seen {catch_number} times."

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.info("[Pipeline] Complete in %.1fms — %s fish_id=%s catch=%d",
                     elapsed_ms, "NEW" if is_new else "RECAPTURE", fish_id, catch_number)

        result = {
            "success": True,
            "fish_id": fish_id,
            "species": species_name,
            "scientific_name": scientific_name,
            "family": family,
            "common_name": species_name,
            "confidence": round(confidence, 3),
            "detection_confidence": round(detection_confidence, 3),
            "match_confidence": round(match_confidence, 3),
            "is_new": is_new,
            "estimated_size_cm": round(float(estimated_size), 1),
            "rarity": rarity,
            "xp_earned": xp_earned,
            "requires_manual_input": ambiguous_recapture,
            "previous_data": previous_data,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            # Czech area system fields
            "area_code": area_code if area_code else None,
            "area_name": area_info["name"] if area_info else None,
            "area_url": area_info.get("url") if area_info else None,
            "species_czech": species_czech,
            "species_english": species_name if species_info else None,
            "catch_number": catch_number,
            "full_history": full_history,
            "user_role": user_role,
            # ReID match debug info
            "match_method": "fishencoder_prototype_topN_vote",
            "roi_images_used": len(cropped_frames),
            "query_images_used": _match_result.query_images_used if _match_result else None,
            "winning_votes": _match_result.winning_votes if _match_result else None,
            "match_margin": round(match_margin_val, 4),
            "ambiguous_recapture": ambiguous_recapture,
        }

        return result


# Singleton
_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Get or create the singleton InferenceService instance."""
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service
