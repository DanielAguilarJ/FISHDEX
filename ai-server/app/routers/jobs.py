import logging
import uuid
import os
import math
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header, Query, Request, UploadFile, File, Form, BackgroundTasks, status

from app.config import settings
from app.database import get_db_connection
from app.services.job_service import process_identification_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

def _validate_auth(
    x_fishdex_client_secret: Optional[str] = None,
    authorization: Optional[str] = None,
) -> None:
    """Validate request authentication via client secret or bearer token."""
    if settings.skip_auth:
        return

    expected_secret = settings.client_secret

    # Check X-FishDex-Client-Secret header
    if x_fishdex_client_secret and x_fishdex_client_secret == expected_secret:
        return

    # Check Authorization Bearer
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == expected_secret:
            return

    raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing credentials")

from app.utils.area_utils import normalize_area_code

@router.post("/upload")
async def upload_job_video(
    video: Optional[UploadFile] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    user_id: str = Form(...),
    area_code: Optional[str] = Form(default=None),
    area_name: Optional[str] = Form(default=None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    species_slug: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    weather: Optional[str] = Form(default=None),
    bite: Optional[str] = Form(default=None),
    size_cm: Optional[float] = Form(default=None),
    fish_state: Optional[str] = Form(default=None),
    custom_name: Optional[str] = Form(default=None),
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Endpoint for the Flutter app to upload raw capture files (photos/videos).
    Saves the file locally on the server disk and registers the job in SQLite.
    """
    _validate_auth(x_fishdex_client_secret, authorization)

    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise HTTPException(
            status_code=422,
            detail="Las coordenadas GPS de la captura no son válidas",
        )

    upload_file = file or video
    if not upload_file:
        raise HTTPException(status_code=400, detail="No se proporcionó ningún archivo (video o file)")

    # MIME / Content-type validation
    content_type = (upload_file.content_type or "").lower().strip()
    original_filename = upload_file.filename or "unknown"
    fname_lower = original_filename.lower()

    # Infer media type: check content-type first, then file extension.
    # application/octet-stream is accepted and falls through to extension check.
    if content_type.startswith("image/") or fname_lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
        media_type = "image"
    elif (
        content_type.startswith("video/")
        or fname_lower.endswith((".mp4", ".mov", ".avi", ".mkv", ".3gp", ".webm"))
    ):
        media_type = "video"
    elif content_type in ("application/octet-stream", "binary/octet-stream", ""):
        # Generic binary — the field is named 'video', so assume video.
        media_type = "video"
        logger.warning(
            f"[upload] Received generic content_type '{content_type}' for file "
            f"'{original_filename}'. Treating as video (field='video')."
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no soportado. Debe ser imagen o video (recibido: {content_type})"
        )

    job_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    
    # Preserve extension
    suffix = Path(original_filename).suffix or (".jpg" if media_type == "image" else ".mp4")
    raw_filename = f"raw_videos/{job_id}_raw{suffix}"
    local_path = Path(settings.server_data_dir) / "storage" / raw_filename
    local_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read content and validate file size
        content = await upload_file.read()
        max_size_bytes = int(settings.max_video_size_mb or 50) * 1024 * 1024
        if len(content) > max_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el límite de tamaño permitido de {settings.max_video_size_mb}MB"
            )

        local_path.write_bytes(content)
        logger.info(f"Saved raw {media_type} for job {job_id} to disk: {local_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to write uploaded capture file to disk: {e}")
        raise HTTPException(status_code=500, detail="Error al escribir el archivo de captura en el disco")

    # Insert job row into SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        area_clean = normalize_area_code(area_code)
        cursor.execute(
            """INSERT INTO identification_jobs (
                id, user_id, status, raw_video_filename, area_code, area_name, 
                latitude, longitude, species_slug, notes,
                weather, bite, size_cm, fish_state, custom_name,
                created_at, media_type, original_filename, content_type, raw_media_filename
            ) VALUES (?, ?, 'uploaded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, user_id, raw_filename, area_clean, area_name,
                latitude, longitude, species_slug, notes,
                weather, bite, size_cm, fish_state, custom_name,
                now_str, media_type, original_filename, content_type, raw_filename
            )
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Clean up file if database registration fails
        if local_path.exists():
            os.remove(local_path)
        logger.error(f"Failed to register job in SQLite: {e}")
        raise HTTPException(status_code=500, detail="Error al registrar el trabajo en la base de datos")
    finally:
        conn.close()

    return {"job_id": job_id}


@router.post("/{job_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def process_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Trigger processing of a registered local job asynchronously."""
    _validate_auth(x_fishdex_client_secret, authorization)

    logger.info(f"Scheduling local job {job_id} for background processing (force={force})")

    # Validate that the job exists before scheduling background task
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status FROM identification_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    current_status = row["status"]
    if current_status == "completed" and not force:
        raise HTTPException(status_code=409, detail=f"Job {job_id} already completed")
    if current_status == "processing" and not force:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is already being processed")

    background_tasks.add_task(process_identification_job, job_id, force=force)

    return {
        "job_id": job_id,
        "status": "processing_started",
    }


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve job details from local SQLite database."""
    _validate_auth(x_fishdex_client_secret, authorization)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM identification_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return dict(row)


@router.get("/{job_id}/result")
async def get_job_result(
    job_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Retrieve the fish sighting result document for a completed job, including previous catch if linked."""
    _validate_auth(x_fishdex_client_secret, authorization)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM identification_jobs WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()

    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    result_sighting_id = job_row["result_sighting_id"]
    if not result_sighting_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Job result sighting ID is missing")

    cursor.execute("SELECT * FROM fish_sightings WHERE id = ?", (result_sighting_id,))
    sighting_row = cursor.fetchone()

    if not sighting_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Sighting result not found")

    sighting_data = dict(sighting_row)
    previous_catch = None

    # Retrieve previous sighting if linked
    prev_id = sighting_data.get("previous_sighting_id")
    if prev_id:
        cursor.execute("SELECT * FROM fish_sightings WHERE id = ?", (prev_id,))
        prev_row = cursor.fetchone()
        if prev_row:
            previous_catch = dict(prev_row)

    conn.close()

    sighting_data["previous_catch"] = previous_catch
    return sighting_data


