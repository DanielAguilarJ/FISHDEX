"""
FishDex AI Server - Router de Identificación
==============================================
Endpoint POST /identify que recibe un video, extrae frames,
ejecuta el modelo y devuelve la identificación del pez.
"""

import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from app.models.schemas import IdentifyResponse, ErrorResponse
from app.services.inference import get_inference_service
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
    """,
)
async def identify_fish(
    video: UploadFile = File(..., description="Video del pez (MP4, MOV, AVI)"),
    latitude: Optional[float] = Form(None, description="Latitud GPS"),
    longitude: Optional[float] = Form(None, description="Longitud GPS"),
    user_id: Optional[str] = Form(None, description="ID del usuario"),
    notes: Optional[str] = Form(None, description="Notas del pescador"),
    confidence_threshold: float = Form(0.70, description="Umbral de confianza para input manual"),
):
    """
    Endpoint principal de identificación de peces.
    
    Flujo:
    1. Recibe el video subido por el usuario
    2. Valida formato y tamaño
    3. Extrae frames del video (10 frames distribuidos uniformemente)
    4. Selecciona el mejor frame (más nítido)
    5. Ejecuta el modelo de IA sobre el frame
    6. Devuelve la identificación con datos gamificados
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
        
        # Extraer frames del video
        frames = extract_frames_from_video(temp_path, max_frames=10)
        
        if not frames:
            raise HTTPException(
                status_code=400,
                detail="No se pudieron extraer frames del video. "
                       "Asegúrate de que el video no está corrupto."
            )
        
        # Seleccionar el mejor frame (más nítido)
        best_frame = select_best_frame(frames)
        
        # Ejecutar inferencia
        service = get_inference_service()
        result = service.identify_fish(best_frame)
        
        # Determinar si requiere input manual basado en el umbral
        result["requires_manual_input"] = result.get("confidence", 0) < confidence_threshold
        
        # Codificar el frame usado en base64 (para preview en la app)
        import cv2
        _, buffer = cv2.imencode(".jpg", best_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
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
