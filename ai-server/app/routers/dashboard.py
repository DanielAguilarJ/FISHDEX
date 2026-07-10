import logging
import os
import time
import json
from pathlib import Path
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
    classifier_loaded = False

    try:
        detector = get_detector_service()
        detector_loaded = detector is not None and bool(getattr(detector, "available", False))
    except Exception as e:
        logger.warning(f"Could not check detector status: {e}")

    try:
        from app.services.classifier_service import get_classifier_service
        classifier = get_classifier_service()
        classifier_loaded = classifier is not None and bool(getattr(classifier, "available", False))
    except Exception as e:
        logger.warning(f"Could not check classifier status: {e}")

    # Aggregated Job stats from local SQLite database
    jobs_summary = {
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0
    }
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM identification_jobs")
        rows = cursor.fetchall()
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
    finally:
        if conn is not None:
            conn.close()

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
                "loaded": classifier_loaded,
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
    """List recent identification jobs from local SQLite, including preview thumbnails."""
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM identification_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        jobs_list = []

        for row in rows:
            d = dict(row)

            # Map SQLite 'id' to '$id' for frontend compatibility
            d["$id"] = d.get("id")

            preview_filename = d.get("preview_filename")

            # If the job does not have a preview yet, try to get it from fish_sightings.
            # IMPORTANT: this query must happen BEFORE conn.close().
            if not preview_filename:
                try:
                    cursor.execute(
                        """
                        SELECT preview_filename
                        FROM fish_sightings
                        WHERE job_id = ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (d.get("id"),),
                    )
                    sighting_preview = cursor.fetchone()

                    if sighting_preview:
                        preview_filename = sighting_preview["preview_filename"]

                except Exception as preview_err:
                    logger.warning(
                        "Could not resolve preview for job %s: %s",
                        d.get("id"),
                        preview_err,
                    )

            d["preview_filename"] = preview_filename

            if preview_filename:
                normalized_preview = preview_filename.replace("\\", "/")
                d["preview_url"] = f"/storage/{normalized_preview}"
            else:
                d["preview_url"] = None

            jobs_list.append(d)

        return jobs_list

    except Exception as e:
        logger.error(f"Failed to list jobs from SQLite: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve jobs from SQLite")

    finally:
        if conn is not None:
            conn.close()

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

def _read_private_json(relative_filename: Optional[str]) -> Optional[dict]:
    if not relative_filename:
        return None

    rel = relative_filename.replace("\\", "/").strip()

    if rel.startswith("/") or ".." in rel:
        raise HTTPException(status_code=400, detail="Invalid private file path")

    private_root = Path(settings.private_data_dir).resolve()
    abs_path = (private_root / rel).resolve()

    if not str(abs_path).startswith(str(private_root)):
        raise HTTPException(status_code=400, detail="Invalid private file path")

    if not abs_path.exists():
        return None

    if abs_path.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Only JSON private files are allowed")

    with open(abs_path, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/jobs/{job_id}/detail")
async def get_dashboard_job_detail(
    job_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM identification_jobs WHERE id = ?", (job_id,))
        job_row = cursor.fetchone()

        if not job_row:
            raise HTTPException(status_code=404, detail="Job not found")

        job = dict(job_row)

        cursor.execute("SELECT * FROM fish_sightings WHERE job_id = ?", (job_id,))
        sighting_row = cursor.fetchone()
        sighting = dict(sighting_row) if sighting_row else None

        individual = None
        fish_id = job.get("result_fish_id") or (sighting.get("fish_id") if sighting else None)
        if fish_id:
            cursor.execute("SELECT * FROM fish_individuals WHERE fish_id = ?", (fish_id,))
            individual_row = cursor.fetchone()
            individual = dict(individual_row) if individual_row else None

        document_filename = job.get("document_filename") or (
            sighting.get("document_filename") if sighting else None
        )

        manifest_filename = None
        if document_filename:
            manifest_filename = document_filename.replace("document.json", "manifest.json")

        document = _read_private_json(document_filename)
        manifest = _read_private_json(manifest_filename)

        return {
            "job": job,
            "sighting": sighting,
            "individual": individual,
            "document": document,
            "manifest": manifest,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch job detail for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job detail")
    finally:
        if conn is not None:
            conn.close()

@router.get("/jobs/{job_id}/document")
async def get_dashboard_job_document(
    job_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT document_filename FROM identification_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        document = _read_private_json(row["document_filename"])

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch job document for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve job document")
    finally:
        if conn is not None:
            conn.close()

@router.get("/fish/{fish_id}/manifest")
async def get_dashboard_fish_manifest(
    fish_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
):
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM fish_sightings WHERE fish_id = ? ORDER BY captured_at DESC", (fish_id,))
        sightings_rows = cursor.fetchall()

        if not sightings_rows:
            raise HTTPException(status_code=404, detail="Fish not found")

        captures = []
        for s_row in sightings_rows:
            sighting = dict(s_row)
            document_filename = sighting.get("document_filename")
            manifest_filename = None
            if document_filename:
                manifest_filename = document_filename.replace("document.json", "manifest.json")
            
            manifest = _read_private_json(manifest_filename)
            captures.append({
                "sighting": sighting,
                "manifest": manifest
            })

        return {
            "fish_id": fish_id,
            "total_captures": len(captures),
            "captures": captures
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch fish manifest for fish {fish_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve fish manifest")
    finally:
        if conn is not None:
            conn.close()
