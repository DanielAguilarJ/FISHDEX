"""
FishDex AI Server - Router de Identificación
==============================================
Endpoint POST /identify que recibe un video, extrae frames,
ejecuta el modelo y devuelve la identificación del pez.
Also includes area search, species listing, and area species endpoints.
"""

import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from typing import Optional

from app.models.schemas import IdentifyResponse, ErrorResponse
from app.services.inference import get_inference_service
from app.services.crop_service import get_crop_service
from app.utils.video import (
    save_temp_video,
    extract_frames_from_video,
    select_best_frame,
    cleanup_temp_file,
    get_video_info,
)

router = APIRouter()

# Tamaño máximo de video: 50MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB en bytes


@router.post(
    "/identify",
    response_model=IdentifyResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Identificar un pez a partir de un video",
    description="""
    Recibe un video corto (5-10 segundos) de un pez, extrae los mejores frames,
    ejecuta el modelo de IA y devuelve la identificación del pez con su historial.
    Now supports full Czech area system with metadata fields.
    """,
)
async def identify_fish(
    video: UploadFile = File(..., description="Video del pez (MP4, MOV, AVI)"),
    area_code: str = Form(..., description="Czech fishing area code e.g. '401 001'"),
    fisherman_id: str = Form(..., description="UUID of the user (from Appwrite)"),
    user_role: str = Form("fisherman", description="'fisherman' or 'researcher'"),
    species: Optional[str] = Form(None, description="Species if already known"),
    fish_state: Optional[str] = Form(None, description="Injury notes or distinguishing marks"),
    name: Optional[str] = Form(None, description="Custom name for the fish"),
    weather: Optional[str] = Form(None, description="Weather conditions"),
    bite: Optional[str] = Form(None, description="Bait or lure used"),
    size: Optional[float] = Form(None, description="Measured size in cm"),
    latitude: Optional[float] = Form(None, description="Latitud GPS"),
    longitude: Optional[float] = Form(None, description="Longitud GPS"),
    confidence_threshold: float = Form(0.70, description="Umbral de confianza para input manual"),
):
    """
    Endpoint principal de identificación de peces.

    Flujo (7-step pipeline):
    0. Receive video → extract frames → delete video
    1. (Optional) Species classification if not provided by user
    2. CROP using fin_detector_best.onnx to isolate fish body
    3. SUBSET the database by filtering server-data/ by AreaCode
    4. SIMILARITY SCORING between cropped fish and existing profiles
    5. DECISION → new fish (new Fish_ID) or recapture (existing Fish_ID)
    6. SEND BACK → researchers get full GPS history, fishermen get restricted
    """
    temp_path = None

    try:
        # Validar tipo de archivo
        allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/avi"]
        if video.content_type and video.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de video no soportado: {video.content_type}. "
                       f"Formatos permitidos: MP4, MOV, AVI"
            )

        # Leer el contenido del video
        video_bytes = await video.read()

        # Validar tamaño
        if len(video_bytes) > MAX_VIDEO_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Video demasiado grande ({len(video_bytes) / 1024 / 1024:.1f}MB). "
                       f"Máximo permitido: {MAX_VIDEO_SIZE / 1024 / 1024:.0f}MB"
            )

        # Guardar video temporalmente para procesarlo con OpenCV
        temp_path = save_temp_video(video_bytes)

        # Obtener info del video
        video_info = get_video_info(temp_path)

        # Validar duración (máximo 15 segundos)
        if video_info.get("duration_seconds", 0) > 15:
            raise HTTPException(
                status_code=400,
                detail="Video demasiado largo. Máximo 15 segundos."
            )

        # Step 0: Extraer frames del video
        frames = extract_frames_from_video(temp_path, max_frames=10)

        if not frames:
            raise HTTPException(
                status_code=400,
                detail="No se pudieron extraer frames del video. "
                       "Asegúrate de que el video no está corrupto."
            )

        # Seleccionar el mejor frame (más nítido)
        best_frame = select_best_frame(frames)

        # Step 2: CROP using ONNX model
        crop_service = get_crop_service()
        cropped_frame = crop_service.crop_fish(best_frame)

        # Build metadata dict
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
        }

        # Ejecutar inferencia with full metadata
        service = get_inference_service()
        result = service.identify_fish(
            frame=cropped_frame,
            area_code=area_code,
            species=species,
            user_role=user_role,
            metadata=metadata,
        )

        # Determinar si requiere input manual basado en el umbral
        result["requires_manual_input"] = result.get("confidence", 0) < confidence_threshold

        # Codificar el frame usado en base64 (para preview en la app)
        import cv2
        _, buffer = cv2.imencode(".jpg", cropped_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_base64 = base64.b64encode(buffer).decode("utf-8")
        result["frame_used"] = frame_base64

        return IdentifyResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al procesar el video: {str(e)}"
        )
    finally:
        # Limpiar archivo temporal
        if temp_path:
            cleanup_temp_file(temp_path)


@router.get(
    "/identify/test",
    response_model=IdentifyResponse,
    summary="Test de identificación (sin video)",
    description="Endpoint de prueba que devuelve una identificación simulada sin necesidad de video.",
)
async def identify_test():
    """
    Endpoint de prueba para verificar que el servicio funciona.
    Devuelve una identificación simulada sin necesidad de subir un video.
    Útil para testing de la app Flutter.
    """
    import numpy as np

    # Crear un frame dummy
    dummy_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    # Ejecutar inferencia con frame dummy
    service = get_inference_service()
    result = service.identify_fish(dummy_frame)
    result["frame_used"] = None  # No hay frame real en test

    return IdentifyResponse(**result)


@router.get(
    "/areas/search",
    summary="Search nearby fishing areas",
    description="Find fishing areas near given GPS coordinates using Haversine distance.",
)
async def search_areas(
    lat: float = Query(..., description="Latitude of current position"),
    lon: float = Query(..., description="Longitude of current position"),
    radius_km: float = Query(10.0, description="Search radius in kilometers"),
):
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
            detail="radius_km must be between 0 and 100"
        )

    areas = find_nearest_areas(lat, lon, max_distance_km=radius_km)
    return {"areas": areas, "count": len(areas), "radius_km": radius_km}


@router.get(
    "/areas/{area_code}/species",
    summary="Get species found in an area",
    description="Returns list of unique species that have been recorded in storage for this area.",
)
async def get_area_species(area_code: str):
    """
    Get list of species found in a specific fishing area's storage.

    Args:
        area_code: Czech fishing area code (with or without space)

    Returns:
        List of species found in that area.
    """
    from app.services.storage_service import get_species_in_area
    from app.data.czech_species import find_species_by_name

    species_slugs = get_species_in_area(area_code)

    # Enrich with species info
    species_list = []
    for slug in species_slugs:
        # Convert slug back to readable name for lookup
        readable = slug.replace("_", " ").title()
        info = find_species_by_name(readable)
        if info:
            species_list.append(info)
        else:
            species_list.append({"slug": slug, "english_name": slug.replace("_", " ").title()})

    return {"area_code": area_code, "species": species_list, "count": len(species_list)}


@router.get(
    "/species",
    summary="Get all Czech fish species",
    description="Returns the complete list of 45 Czech fish species for dropdown population.",
)
async def get_all_species():
    """
    Get the complete list of Czech fish species.

    Returns:
        List of all 45 species with Czech, English, and Latin names.
    """
    from app.data.czech_species import get_all_species

    species = get_all_species()
    return {"species": species, "count": len(species)}
