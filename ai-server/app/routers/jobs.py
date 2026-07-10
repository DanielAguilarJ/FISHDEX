import logging
import uuid
import os
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

@router.post("/upload")
async def upload_job_video(
    video: UploadFile = File(...),
    user_id: str = Form(...),
    area_code: Optional[str] = Form(default=None),
    area_name: Optional[str] = Form(default=None),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    species_slug: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Endpoint for the Flutter app to upload raw capture videos.
    Saves the video locally on the server disk and registers the job in SQLite.
    """
    _validate_auth(x_fishdex_client_secret, authorization)

    job_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    
    # Define local file storage path
    raw_video_filename = f"raw_videos/{job_id}_raw.mp4"
    local_video_path = Path(settings.server_data_dir) / "storage" / raw_video_filename
    local_video_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Save video bytes to disk
        content = await video.read()
        local_video_path.write_bytes(content)
        logger.info(f"Saved raw video for job {job_id} to disk: {local_video_path}")
    except Exception as e:
        logger.error(f"Failed to write uploaded video file to disk: {e}")
        raise HTTPException(status_code=500, detail="Error al escribir el archivo de video en el disco")

    # Insert job row into SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO identification_jobs (
                id, user_id, status, raw_video_filename, area_code, area_name, 
                latitude, longitude, species_slug, notes, created_at
            ) VALUES (?, ?, 'uploaded', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, user_id, raw_video_filename, area_code, area_name,
                latitude, longitude, species_slug, notes, now_str
            )
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Clean up video file if database registration fails
        if local_video_path.exists():
            os.remove(local_video_path)
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
    """Retrieve the fish sighting result document for a completed job."""
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
    conn.close()

    if not sighting_row:
        raise HTTPException(status_code=404, detail="Sighting result not found")

    return dict(sighting_row)
