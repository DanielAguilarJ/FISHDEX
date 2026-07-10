import logging
import os
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query

from app.config import settings
from app.database import get_db_connection
from app.services.system_monitor import get_system_stats
from app.services.job_service import process_identification_job
from app.services.detector_service import get_detector_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

def _validate_dashboard_auth(
    x_fishdex_dashboard_secret: Optional[str] = None,
    secret: Optional[str] = None,
) -> None:
    """Validate request authentication for dashboard endpoints."""
    if settings.skip_auth:
        return

    expected_secret = settings.dashboard_secret

    # Check header
    if x_fishdex_dashboard_secret and x_fishdex_dashboard_secret == expected_secret:
        return

    # Check query param
    if secret and secret == expected_secret:
        return

    raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing dashboard secret")

@router.get("/status")
async def get_dashboard_status(
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    """Retrieve detailed server metrics and local SQLite job stats."""
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    # System metrics
    stats = get_system_stats()

    # Model status
    detector_loaded = False
    try:
        detector = get_detector_service()
        detector_loaded = detector is not None and detector.is_available()
    except Exception:
        pass

    # Aggregated Job stats from local SQLite database
    jobs_summary = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0
    }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM identification_jobs")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            status = row["status"]
            if status in ("uploaded", "queued"):
                jobs_summary["queued"] += 1
            elif status in ("processing", "extracting_frames", "detecting_fish", "cropping_fish", "classifying_species", "matching_individual", "uploading_results"):
                jobs_summary["processing"] += 1
            elif status in ("completed", "needs_review"):
                jobs_summary["completed"] += 1
            elif status == "failed":
                jobs_summary["failed"] += 1
    except Exception as e:
        logger.error(f"Failed to fetch jobs summary from SQLite: {e}")

    return {
        "status": "online",
        **stats,
        "models": {
            "detector": {
                "loaded": detector_loaded,
                "type": settings.detector_type,
                "path": settings.detector_model_path
            },
            "classifier": {
                "loaded": False,
                "path": settings.classifier_model_path
            }
        },
        "jobs": jobs_summary
    }

@router.get("/jobs")
async def get_dashboard_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    """List recent identification jobs from local SQLite."""
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM identification_jobs ORDER BY created_at DESC LIMIT ?", 
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()

        jobs_list = []
        for row in rows:
            d = dict(row)
            # Map sqlite 'id' to '$id' for frontend index.html compatibility
            d["$id"] = d["id"]
            jobs_list.append(d)
            
        return jobs_list
    except Exception as e:
        logger.error(f"Failed to list jobs from SQLite: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve jobs from SQLite")

@router.post("/jobs/{job_id}/retry")
async def retry_dashboard_job(
    job_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    """Force reprocessing of a failed job."""
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    try:
        result = process_identification_job(job_id, force=True)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Failed to retry job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
