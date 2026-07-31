import asyncio
import logging
import json
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Header, Query

from app.config import settings
from app.database import get_db_connection
from app.security import constant_time_compare
from app.services.system_monitor import get_system_stats
from app.services.job_service import process_identification_job
from app.services.detector_service import get_detector_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Statuses a job row may hold. Used to validate the dashboard filter so a typo
# returns 400 rather than an empty list that looks like "no jobs".
JOB_STATUSES: frozenset[str] = frozenset(
    {
        "uploaded",
        "processing",
        "pending_crop",
        "completed",
        "repeat_capture",
        "needs_manual_review",
        "failed",
    }
)

def _validate_dashboard_auth(
    x_fishdex_dashboard_secret: Optional[str] = None,
    secret: Optional[str] = None,
) -> None:
    """
    Validate authentication for dashboard endpoints.

    Comparisons are constant-time so the secret cannot be recovered by measuring
    response latency.

    Args:
        x_fishdex_dashboard_secret: Value of the ``X-FishDex-Dashboard-Secret``
            header. This is the preferred transport.
        secret: Same secret supplied as a query parameter. Supported for the
            existing dashboard, but discouraged: query strings end up in proxy
            access logs and browser history.

    Raises:
        HTTPException 401: Neither credential matched.
    """
    if settings.skip_auth:
        return

    expected_secret = settings.dashboard_secret

    if constant_time_compare(x_fishdex_dashboard_secret, expected_secret):
        return

    if constant_time_compare(secret, expected_secret):
        logger.info(
            "Dashboard authenticated via query parameter; prefer the "
            "X-FishDex-Dashboard-Secret header."
        )
        return

    raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing dashboard secret")

@router.get("/status")
async def get_dashboard_status(
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
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
    except Exception as e:  # noqa: BLE001 — a diagnostic endpoint reports partial status rather than 500
        logger.warning(f"Could not check detector status: {e}")

    try:
        from app.services.classifier_service import get_classifier_service
        classifier = get_classifier_service()
        classifier_loaded = classifier is not None and bool(getattr(classifier, "available", False))
    except Exception as e:  # noqa: BLE001 — a diagnostic endpoint reports partial status rather than 500
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
    except Exception as e:  # noqa: BLE001 — a diagnostic endpoint reports partial status rather than 500
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
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    List identification jobs from local SQLite with pagination and status filtering.

    Args:
        limit: Page size, 1-500.
        offset: Page offset.
        status: Optional status filter; must be one of :data:`JOB_STATUSES`.
        x_fishdex_dashboard_secret: Dashboard secret header.
        secret: Dashboard secret query parameter (legacy).

    Returns:
        Dict with ``jobs``, ``total``, ``limit``, ``offset`` and ``has_more``.

    Raises:
        HTTPException 400: Unknown status filter.
        HTTPException 401: Invalid dashboard secret.
        HTTPException 500: Query failure.
    """
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    if status is not None and status not in JOB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown status filter. Allowed: {sorted(JOB_STATUSES)}",
        )

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # The only interpolated fragment is one of two fixed literals chosen by a
        # boolean; the client-supplied `status` value travels as a bound parameter.
        # Ruff cannot see that, hence the suppressions below.
        where_clause = "WHERE status = ?" if status else ""
        count_params = (status,) if status else ()
        query_params = (status, limit, offset) if status else (limit, offset)

        # Get total count for pagination metadata
        cursor.execute(
            f"SELECT COUNT(*) FROM identification_jobs {where_clause}",  # noqa: S608
            count_params,
        )
        total_count = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT *
            FROM identification_jobs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,  # noqa: S608
            query_params,
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

                except Exception as preview_err:  # noqa: BLE001 — a diagnostic endpoint reports partial status rather than 500
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

        return {
            "jobs": jobs_list,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count,
        }

    except Exception as e:
        logger.error(f"Failed to list jobs from SQLite: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve jobs from SQLite") from e

    finally:
        if conn is not None:
            conn.close()

@router.post("/jobs/{job_id}/retry")
async def retry_dashboard_job(
    job_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    Force reprocessing of a failed job.

    ``process_identification_job`` is synchronous and runs model inference for
    seconds to minutes. Calling it directly from this async handler blocked the
    event loop and froze every other request, so it is dispatched to a worker
    thread instead.

    Args:
        job_id: Job to reprocess.
        x_fishdex_dashboard_secret: Dashboard secret header.
        secret: Dashboard secret as a query parameter (legacy).

    Returns:
        Dict with the processing outcome.

    Raises:
        HTTPException 401: Invalid dashboard secret.
        HTTPException 500: Processing failed.
    """
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    try:
        result = await asyncio.to_thread(process_identification_job, job_id, force=True)
    except Exception as exc:
        logger.error("Failed to retry job %s: %s", job_id, exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="No se pudo reprocesar el trabajo"
        ) from exc
    return {"status": "success", "result": result}

def _read_private_json(relative_filename: Optional[str]) -> Optional[dict]:
    """
    Read a JSON document from the private data directory.

    Args:
        relative_filename: Path relative to the private data root.

    Returns:
        Parsed document, or None when no filename was supplied.

    Raises:
        HTTPException 400: The path escapes the private root.
    """
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
) -> dict[str, Any]:
    """
    Return the full record for one job, including artifacts and linkage.

    Args:
        job_id: Job to inspect.
        x_fishdex_dashboard_secret: Dashboard secret header.
        secret: Dashboard secret query parameter (legacy).

    Returns:
        Job row enriched with its stored documents.
    """
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
        raise HTTPException(status_code=500, detail="Failed to retrieve job detail") from e
    finally:
        if conn is not None:
            conn.close()

@router.get("/jobs/{job_id}/document")
async def get_dashboard_job_document(
    job_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    Return the stored identification document for a job.

    Args:
        job_id: Job to inspect.
        x_fishdex_dashboard_secret: Dashboard secret header.
        secret: Dashboard secret query parameter (legacy).

    Returns:
        The parsed document.
    """
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
        raise HTTPException(status_code=500, detail="Failed to retrieve job document") from e
    finally:
        if conn is not None:
            conn.close()

@router.get("/fish/{fish_id}/manifest")
async def get_dashboard_fish_manifest(
    fish_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    Return the artifact manifest for one fish identity.

    Args:
        fish_id: Fish identifier.
        x_fishdex_dashboard_secret: Dashboard secret header.
        secret: Dashboard secret query parameter (legacy).

    Returns:
        The parsed manifest.
    """
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
        raise HTTPException(status_code=500, detail="Failed to retrieve fish manifest") from e
    finally:
        if conn is not None:
            conn.close()


@router.get("/fish/{fish_id}/timeline")
async def get_dashboard_fish_timeline(
    fish_id: str,
    x_fishdex_dashboard_secret: Optional[str] = Header(default=None, alias="X-FishDex-Dashboard-Secret"),
    secret: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """
    Returns a chronological list of all captures (sightings) for a given fish_id.
    Includes location coordinates, dates, user IDs, media URLs, weather, size, etc.
    Useful for displaying a fish's trajectory and growth over time on a map.
    """
    _validate_dashboard_auth(x_fishdex_dashboard_secret, secret)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM fish_sightings
            WHERE fish_id = ?
            ORDER BY catch_number ASC, captured_at ASC
            """,
            (fish_id,),
        )
        rows = cursor.fetchall()
        
        timeline_events = []
        for r in rows:
            event = dict(r)
            preview_filename = event.get("preview_filename")
            if preview_filename:
                clean_preview = preview_filename.replace('\\', '/')
                event["preview_url"] = f"/storage/{clean_preview}"
            else:
                event["preview_url"] = None

            video_filename = event.get("video_filename")
            if video_filename:
                clean_video = video_filename.replace('\\', '/')
                event["video_url"] = f"/storage/{clean_video}"
            else:
                event["video_url"] = None

            timeline_events.append(event)

        return {
            "fish_id": fish_id,
            "total_captures": len(timeline_events),
            "timeline": timeline_events
        }

    except Exception as e:
        logger.error(f"Failed to fetch fish timeline for fish {fish_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve fish timeline") from e
    finally:
        if conn is not None:
            conn.close()

