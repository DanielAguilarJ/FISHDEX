"""
Jobs Router - FastAPI endpoints for the job-based identification pipeline.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.services.appwrite_service import get_appwrite_service
from app.services.job_service import process_identification_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
limiter = Limiter(key_func=get_remote_address)


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


@router.post("/{job_id}/process")
@limiter.limit("5/minute")
async def process_job(
    request: Request,
    job_id: str,
    force: bool = Query(default=False, description="Force reprocessing of completed/failed jobs"),
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Trigger processing of an identification job.

    Downloads the video, runs detection/classification/matching pipeline,
    and persists results to Appwrite.
    """
    _validate_auth(x_fishdex_client_secret, authorization)

    logger.info(f"Processing job {job_id} (force={force})")

    try:
        result = process_identification_job(job_id, force=force)
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "already completed" in error_msg.lower() or "already being processed" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        else:
            logger.error(f"Job {job_id} processing error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        logger.error(f"Job {job_id} processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Processing failed",
                "message": str(e)[:500],
                "job_id": job_id,
            },
        )


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """Get the current state of an identification job."""
    _validate_auth(x_fishdex_client_secret, authorization)

    appwrite = get_appwrite_service()

    try:
        job_doc = appwrite.get_document(
            database_id=settings.appwrite_database_id,
            collection_id="identification_jobs",
            document_id=job_id,
        )
    except Exception as e:
        logger.error(f"Failed to fetch job {job_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if not job_doc:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return job_doc


@router.get("/{job_id}/result")
async def get_job_result(
    job_id: str,
    x_fishdex_client_secret: Optional[str] = Header(default=None, alias="X-FishDex-Client-Secret"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Get the fish sighting result linked to a completed job.

    Returns the fish_sightings document referenced by the job's result_sighting_id.
    """
    _validate_auth(x_fishdex_client_secret, authorization)

    appwrite = get_appwrite_service()

    # Fetch the job first
    try:
        job_doc = appwrite.get_document(
            database_id=settings.appwrite_database_id,
            collection_id="identification_jobs",
            document_id=job_id,
        )
    except Exception as e:
        logger.error(f"Failed to fetch job {job_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if not job_doc:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Check job is completed and has a result
    status = job_doc.get("status")
    result_sighting_id = job_doc.get("result_sighting_id")

    if status not in ("completed", "needs_review"):
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} has not completed processing (status: {status})",
        )

    if not result_sighting_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} has no associated sighting result",
        )

    # Fetch the sighting document
    try:
        sighting_doc = appwrite.get_document(
            database_id=settings.appwrite_database_id,
            collection_id="fish_sightings",
            document_id=result_sighting_id,
        )
    except Exception as e:
        logger.error(f"Failed to fetch sighting {result_sighting_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Sighting {result_sighting_id} not found",
        )

    if not sighting_doc:
        raise HTTPException(
            status_code=404,
            detail=f"Sighting {result_sighting_id} not found",
        )

    return sighting_doc
