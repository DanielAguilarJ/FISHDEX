"""
FishDex AI Server - Router de Identificación
==============================================
POST /api/v1/identify — 7-step pipeline (video → frames → crop → subset → similarity → decision → response)
GET  /api/v1/identify/test — test endpoint with dummy frame
GET  /api/v1/areas/search — nearby area search
GET  /api/v1/areas/{area_code}/species — species in area storage
GET  /api/v1/areas/{area_code}/stats — area statistics
GET  /api/v1/species — all Czech fish species
GET  /api/v1/fish/{fish_id}/history — catch history for a fish
GET  /api/v1/health/detailed — detailed server health info
"""

import base64
import logging
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.middleware.auth import AuthenticatedUser, verify_auth
from app.models.schemas import ErrorResponse, IdentifyResponse
from app.services.obb_roi_service import get_obb_roi_service
from app.services.inference import get_inference_service
from pathlib import Path
from app.utils.video import (
    cleanup_temp_file,
    extract_frames_from_video,
    get_video_info,
    save_temp_video,
    select_best_n_frames,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# LEGACY ENDPOINT — this router implements the old /api/v1/identify flow which
# uses inference.py, similarity_service.py, and storage_service.py.
#
# The CANONICAL identification flow is /api/v1/jobs/{id}/process which calls
# IdentificationPipeline (identification_pipeline.py → identity_scoring_service.py
# → identity_decision_service.py). That pipeline includes:
# - similarity_reference traceability
# - two-level geographic search
# - re-match under BEGIN IMMEDIATE lock
# - proper calibration gating
#
# This endpoint is kept for backward compatibility but should be migrated to
# use the unified pipeline. Do NOT add new features here.
# ──────────────────────────────────────────────────────────────────────────────
router = APIRouter()

# Rate limiter (uses the instance stored on app.state by main.py)
limiter = Limiter(key_func=get_remote_address)

# Tamaño máximo de video (from config)
MAX_VIDEO_SIZE = settings.max_video_size_mb * 1024 * 1024


# =========================================================================
# POST /api/v1/identify — MAIN PIPELINE
# =========================================================================
@router.post(
    "/identify",
    response_model=IdentifyResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Identify a fish from a video or image",
    description="""
    Receives a short video (5-10 seconds) or a still image of a fish.
    For videos, extracts the best frames. For images, uses the image directly.
    Crops the fish body using YOLO OBB, compares against existing fish
    profiles in the same area using FishEncoder prototype matching,
    and returns identification with full history.
    Requires authentication (Bearer token or client secret).
    """,
)
@limiter.limit("10/minute")
async def identify_fish(
    request: Request,
    video: UploadFile = File(..., description="Video of the fish (MP4, MOV, AVI)"),
    area_code: str = Form(..., description="Czech fishing area code e.g. '401 001'"),
    user_role: str = Form("fisherman", description="'fisherman' or 'researcher'"),
    species: Optional[str] = Form(None, description="Species if already known"),
    fish_state: Optional[str] = Form(None, description="Injury notes or distinguishing marks"),
    name: Optional[str] = Form(None, description="Custom name for the fish"),
    weather: Optional[str] = Form(None, description="Weather conditions"),
    bite: Optional[str] = Form(None, description="Bait or lure used"),
    size: Optional[float] = Form(None, description="Measured size in cm"),
    latitude: Optional[float] = Form(None, description="GPS latitude"),
    longitude: Optional[float] = Form(None, description="GPS longitude"),
    confidence_threshold: float = Form(0.70, description="Confidence threshold for manual input flag"),
    current_user: AuthenticatedUser = Depends(verify_auth),
) -> IdentifyResponse:
    """
    7-step fish identification pipeline.

    Steps:
      0. Receive video/image → extract frames → select best frames
      1. Species lookup (from user input or mark unknown)
      2. OBB ROI: extract and deskew fish ROI from each frame (YOLO OBB .pt)
      3. SUBSET: find existing fish in this area/species for comparison
      4. SIMILARITY: FishEncoder prototype top-N vote against subset
      5. DECISION: new fish or recapture based on reid_similarity_threshold
      6. SAVE: ROI frames + reid embeddings to server-data/
      7. RESPOND: role-filtered history in IdentifyResponse
    """
    temp_path: Optional[str] = None

    try:
        # ── Detect file type: check content_type AND filename extension ──
        filename = video.filename or ""
        suffix = Path(filename).suffix.lower()

        _image_content_types = {"image/jpeg", "image/png", "image/webp"}
        _image_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
        _video_content_types = {
            "video/mp4", "video/quicktime", "video/x-msvideo",
            "video/avi", "video/webm",
        }
        _video_suffixes = {".mp4", ".mov", ".avi", ".webm"}
        _unknown_ct = video.content_type in (None, "", "application/octet-stream")

        is_image = (
            video.content_type in _image_content_types
            or suffix in _image_suffixes
        )
        is_video = (
            video.content_type in _video_content_types
            or suffix in _video_suffixes
            or (_unknown_ct and suffix not in _image_suffixes)
        )

        if not is_image and not is_video:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: content_type={video.content_type!r} "
                       f"filename={filename!r}. "
                       f"Allowed: MP4, MOV, AVI, WebM, JPEG, PNG, WebP",
            )

        # ── Read bytes ──
        video_bytes = await video.read()

        if len(video_bytes) > MAX_VIDEO_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(video_bytes) / 1024 / 1024:.1f}MB). "
                       f"Max: {settings.max_video_size_mb}MB",
            )

        # ── Step 0: Extract frames (bifurcation image vs video) ──
        if is_image:
            np_bytes = np.frombuffer(video_bytes, np.uint8)
            frame = cv2.imdecode(np_bytes, cv2.IMREAD_COLOR)
            if frame is None:
                raise HTTPException(
                    status_code=400,
                    detail="Could not decode image. File may be corrupt or unsupported.",
                )
            best_frames = [frame]
            logger.info("[Step 0] Image input decoded: %s", filename)
        else:
            # Use real extension so ffmpeg/OpenCV recognise the container
            video_suffix = suffix if suffix in _video_suffixes else ".mp4"
            temp_path = save_temp_video(video_bytes, suffix=video_suffix)
            logger.info(
                "[Step 0] Video temp saved: %s (%.1f MB)",
                temp_path,
                len(video_bytes) / 1024 / 1024,
            )

            video_info = get_video_info(temp_path)
            if video_info.get("duration_seconds", 0) > settings.max_video_duration_seconds:
                raise HTTPException(
                    status_code=400,
                    detail=f"Video too long. Max {settings.max_video_duration_seconds} seconds.",
                )

            all_frames = extract_frames_from_video(
                temp_path,
                max_frames=settings.max_frames_to_extract,
                max_side=settings.frame_max_side,
            )
            if not all_frames:
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract frames from video. File may be corrupt.",
                )

            best_frames = select_best_n_frames(all_frames, n=settings.max_frames_to_save)
            logger.info(
                "[Step 0] Video: extracted %d frames, selected best %d",
                len(all_frames),
                len(best_frames),
            )

            cleanup_temp_file(temp_path)
            temp_path = None

        # ── Step 2: OBB ROI extraction (YOLO OBB .pt) ──
        roi_service = get_obb_roi_service()
        cropped_frames: list[np.ndarray] = []
        roi_confidences: list[float] = []
        roi_failures: list[str] = []

        for i, frame in enumerate(best_frames):
            result = roi_service.extract_roi(frame)
            if result.qualified and result.roi is not None:
                cropped_frames.append(result.roi)
                roi_confidences.append(result.confidence)
            else:
                roi_failures.append(f"frame_{i}: {result.reason}")
                logger.debug("[Step 2] ROI not qualified for frame %d: %s", i, result.reason)

        if not cropped_frames:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "No qualified fish ROI found in any frame. "
                               "Ensure the fish is clearly visible in the image/video.",
                    "failures": roi_failures,
                },
            )

        logger.info(
            "[Step 2] OBB ROI: %d/%d frames qualified  avg_conf=%.2f",
            len(cropped_frames),
            len(best_frames),
            sum(roi_confidences) / len(roi_confidences),
        )

        # ── Build metadata dict (use authenticated user_id, not form field) ──
        fisherman_id = current_user.user_id
        metadata = {
            "area_code": area_code,
            "fisherman_id": fisherman_id,
            "user_role": user_role,
            "species": species,
            "fish_state": fish_state,
            "name": name,
            "weather": weather,
            "bite": bite,
            "size": size,
            "latitude": latitude,
            "longitude": longitude,
            # ROI pipeline metadata — consumed by inference.py
            "_roi_confidences": roi_confidences,
            "_roi_failures": roi_failures,
        }

        # ── Steps 3-7: Run inference pipeline ──
        service = get_inference_service()
        result = service.identify_fish(
            cropped_frames=cropped_frames,
            area_code=area_code,
            species=species,
            user_role=user_role,
            metadata=metadata,
        )

        # ── Confidence threshold check ──
        result["requires_manual_input"] = result.get("confidence", 0) < confidence_threshold

        # ── Encode first cropped frame as base64 preview ──
        if cropped_frames:
            _, buffer = cv2.imencode(
                ".jpg", cropped_frames[0],
                [cv2.IMWRITE_JPEG_QUALITY, 85],
            )
            result["frame_used"] = base64.b64encode(buffer).decode("utf-8")
        else:
            result["frame_used"] = None

        return IdentifyResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("identify_fish failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing video: {str(e)}",
        )
    finally:
        if temp_path:
            cleanup_temp_file(temp_path)


# =========================================================================
# GET /api/v1/identify/test — Test endpoint (no video needed)
# =========================================================================
@router.get(
    "/identify/test",
    response_model=IdentifyResponse,
    summary="Test identification (no video)",
    description="Returns a simulated identification without uploading a video.",
)
async def identify_test() -> IdentifyResponse:
    """
    Test endpoint that runs the pipeline with dummy frames.
    Useful for verifying the server is working from the Flutter app.
    """
    try:
        # Create 5 dummy frames
        dummy_frames = [
            np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            for _ in range(5)
        ]

        service = get_inference_service()
        result = service.identify_fish(
            cropped_frames=dummy_frames,
            area_code="401 001",
            species="Common carp",
            user_role="fisherman",
            metadata={"fisherman_id": "test-user", "species": "Common carp"},
        )
        result["frame_used"] = None
        return IdentifyResponse(**result)
    except Exception as e:
        logger.error("identify_test failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# GET /api/v1/fish/{fish_id}/history — Fish catch history
# =========================================================================
@router.get(
    "/fish/{fish_id}/history",
    summary="Get catch history for a fish",
    description="Returns full catch history for a specific fish. "
                "Researchers get GPS coords; fishermen do not.",
)
async def get_fish_history_endpoint(
    fish_id: str,
    user_role: str = Query("fisherman", description="'fisherman' or 'researcher'"),
) -> dict:
    """
    Look up a fish by its ID and return its complete catch history.

    Args:
        fish_id:   Unique fish identifier (e.g. "CZ-401001-CYPCA-0001").
        user_role: Determines if GPS coordinates are included.

    Returns:
        Dict with fish_id, area_code, species_slug, total_catches, and history list.
    """
    from app.services.storage_service import get_fish_history_by_id, get_restricted_history

    result = get_fish_history_by_id(fish_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fish {fish_id} not found")

    # Role-based filtering
    if user_role != "researcher":
        result["history"] = get_restricted_history(result["history"])

    return result


# =========================================================================
# GET /api/v1/areas/{area_code}/stats — Area statistics
# =========================================================================
@router.get(
    "/areas/{area_code}/stats",
    summary="Get area statistics",
    description="Returns total fish count, species breakdown, and most recent catch date for an area.",
)
async def get_area_stats_endpoint(area_code: str) -> dict:
    """
    Compute statistics for a fishing area's stored data.

    Args:
        area_code: Czech fishing area code (e.g. "401001" or "401 001").

    Returns:
        Dict with total_fish, species_breakdown, most_recent_catch, total_catches.
    """
    from app.services.storage_service import get_area_stats

    stats = get_area_stats(area_code)

    # Enrich with area name if available
    try:
        from app.data.czech_areas import find_area_by_code
        area_info = find_area_by_code(area_code)
        if area_info:
            stats["area_name"] = area_info["name"]
    except Exception:
        pass

    return stats


# =========================================================================
# GET /api/v1/health/detailed — Detailed health check
# =========================================================================
@router.get(
    "/health/detailed",
    summary="Detailed health check",
    description="Returns model status, total fish in database, area count, and disk usage.",
)
async def health_detailed() -> dict:
    """
    Detailed health check with model status and database stats.

    Returns:
        Dict with status, model info, fish count, disk usage.
    """
    from app.services.obb_roi_service import _obb_roi_service
    from app.services.reid_embedding_service import _reid_embedding_service
    from app.services.storage_service import get_disk_usage_mb, get_total_fish_count
    from pathlib import Path as _Path

    # Check model loaded status without forcing a heavyweight load
    obb_loaded = _obb_roi_service is not None and _obb_roi_service.is_loaded
    reid_loaded = _reid_embedding_service is not None and _reid_embedding_service.is_loaded

    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": "3.0.0",
        "match_method": "fishencoder_prototype_topN_vote",
        # OBB ROI model
        "obb_model_configured": _Path(settings.obb_model_path).is_file(),
        "obb_model_loaded": obb_loaded,
        # ReID model
        "reid_model_configured": _Path(settings.reid_model_path).is_file(),
        "reid_model_loaded": reid_loaded,
        "reid_model_name": settings.reid_model_name,
        "reid_embedding_dim": settings.reid_embedding_dim,
        "reid_similarity_threshold": settings.reid_similarity_threshold,
        # Database
        "total_fish_in_database": get_total_fish_count(),
        "disk_usage_mb": get_disk_usage_mb(),
        "nearby_area_radius_km": settings.nearby_area_radius_km,
    }


# =========================================================================
# GET /api/v1/areas/search — Search nearby areas
# =========================================================================
@router.get(
    "/areas/search",
    summary="Search nearby fishing areas",
    description="Find fishing areas near given GPS coordinates using Haversine distance.",
)
async def search_areas(
    lat: float = Query(..., description="Latitude of current position"),
    lon: float = Query(..., description="Longitude of current position"),
    radius_km: float = Query(10.0, description="Search radius in kilometers"),
) -> dict:
    """
    Search for fishing areas near the given GPS coordinates.

    Args:
        lat: Latitude of current position
        lon: Longitude of current position
        radius_km: Maximum search radius in km (default 10)

    Returns:
        List of nearby fishing areas with distance information.
    """
    from app.data.czech_areas import find_nearest_areas

    if radius_km <= 0 or radius_km > 100:
        raise HTTPException(
            status_code=400,
            detail="radius_km must be between 0 and 100",
        )

    areas = find_nearest_areas(lat, lon, max_distance_km=radius_km)
    return {"areas": areas, "count": len(areas), "radius_km": radius_km}


# =========================================================================
# GET /api/v1/areas/{area_code}/species — Species in area
# =========================================================================
@router.get(
    "/areas/{area_code}/species",
    summary="Get species found in an area",
    description="Returns list of unique species that have been recorded in storage for this area.",
)
async def get_area_species(area_code: str) -> dict:
    """
    Get list of species found in a specific fishing area's storage.

    Args:
        area_code: Czech fishing area code (with or without space)

    Returns:
        List of species found in that area.
    """
    from app.data.czech_species import find_species_by_name
    from app.services.storage_service import get_species_in_area

    species_slugs = get_species_in_area(area_code)

    species_list = []
    for slug in species_slugs:
        readable = slug.replace("_", " ").title()
        info = find_species_by_name(readable)
        if info:
            species_list.append(info)
        else:
            species_list.append({"slug": slug, "english_name": readable})

    return {"area_code": area_code, "species": species_list, "count": len(species_list)}


# =========================================================================
# GET /api/v1/species — All Czech species
# =========================================================================
@router.get(
    "/species",
    summary="Get all Czech fish species",
    description="Returns the complete list of 45 Czech fish species for dropdown population.",
)
async def get_all_species() -> dict:
    """
    Get the complete list of Czech fish species.

    Returns:
        List of all 45 species with Czech, English, and Latin names.
    """
    from app.data.czech_species import get_all_species

    species = get_all_species()
    return {"species": species, "count": len(species)}
