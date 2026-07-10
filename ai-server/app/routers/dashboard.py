import logging
import os
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query

from app.config import settings
from app.services.appwrite_service import get_appwrite_service
from app.services.system_monitor import get_system_stats
from app.services.job_service import process_identification_job
from app.services.detector_service import get_detector_service
from appwrite.query import Query as AppwriteQuery

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
    """Retrieve detailed server metrics and Appwrite job stats."""
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

    # Aggregated Job stats from Appwrite (fetch last 100 to calculate aggregates quickly)
    appwrite = get_appwrite_service()
    jobs_summary = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0
    }
    
    try:
        recent_jobs = appwrite.list_documents(
            collection_id="identification_jobs",
            queries=[AppwriteQuery.limit(100), AppwriteQuery.order_desc("created_at")]
        )
        for job in recent_jobs:
            status = job.get("status")
            if status in ("uploaded", "queued"):
                jobs_summary["queued"] += 1
            elif status in ("processing", "extracting_frames", "detecting_fish", "cropping_fish", "classifying_species", "matching_individual", "uploading_results", "updating_appwrite"):
                jobs_summary["processing"] += 1
            elif status in ("completed", "needs_review"):
                jobs_summary["completed"] += 1
            elif status == "failed":
                jobs_summary["failed"] += 1
    except Exception as e:
        logger.error(f"Failed to fetch jobs summary: {e}")

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
    """List recent identification jobs from Appwrite."""
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    appwrite = get_appwrite_service()
    try:
        jobs = appwrite.list_documents(
            collection_id="identification_jobs",
            queries=[
                AppwriteQuery.order_desc("created_at"),
                AppwriteQuery.limit(limit)
            ]
        )
        return jobs
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve jobs from Appwrite")

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
