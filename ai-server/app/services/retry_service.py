"""
FishDex AI Server — Background Crop Retry Service
===================================================
Periodically retries fish detection on jobs stuck in 'pending_crop' status.

Strategy:
  - Every 60 seconds, scan for pending_crop jobs with retry_count < 3
  - Each retry: extract MORE frames (15-20) and lower threshold progressively
  - Retry 1: threshold 0.20, 15 frames
  - Retry 2: threshold 0.15, 20 frames
  - Retry 3: threshold 0.15, 20 frames, relaxed area guard (0.75)
  - If all 3 background retries fail: mark as 'failed' with error message
  - If any retry succeeds: inject the recovered detection into the complete
    identification pipeline so embeddings, matching, sightings and artifacts
    are generated normally
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings
from app.database import get_db_connection
from app.utils.crop_utils import crop_fish_best
from app.utils.video import iter_frames_from_video, DecodedVideoFrame

logger = logging.getLogger(__name__)

_retry_task: Optional[asyncio.Task] = None

# Retry configurations: (threshold, max_area_ratio)
RETRY_CONFIGS = [
    (0.20, 0.65),
    (0.15, 0.65),
    (0.15, 0.75),
]



def _is_valid_tight(detection, frame_shape, min_conf: float, max_area: float) -> bool:
    """Validate detection for retry: confidence + area ratio check."""
    if detection is None:
        return False

    conf = float(getattr(detection, "confidence", 0.0))
    if conf < min_conf:
        return False

    polygon = getattr(detection, "polygon", None)
    if not polygon or len(polygon) < 4:
        return False

    h, w = frame_shape[:2]
    frame_area = float(h * w)
    if frame_area <= 0:
        return False

    pts = np.array([[p[0], p[1]] for p in polygon[:4]], dtype=np.float32)
    obb_area = abs(float(cv2.contourArea(pts)))
    ratio = obb_area / frame_area

    if ratio < 0.001 or ratio > max_area:
        return False

    return True


async def _retry_pending_crops():
    """Background loop: retry pending_crop jobs every 60 seconds."""
    logger.info("Crop retry service started")

    # Wait 30s after server start before first scan
    await asyncio.sleep(30)

    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """SELECT id, raw_media_filename, media_type, retry_count
                   FROM identification_jobs
                   WHERE status = 'pending_crop' AND (retry_count IS NULL OR retry_count < 3)
                   ORDER BY created_at ASC
                   LIMIT 5"""
            )
            pending_jobs = cursor.fetchall()
            conn.close()

            if pending_jobs:
                logger.info(f"Crop retry: found {len(pending_jobs)} pending jobs")

            for job_row in pending_jobs:
                job_id = job_row["id"]
                raw_filename = job_row["raw_media_filename"]
                media_type = job_row["media_type"] or "video"
                retry_count = int(job_row["retry_count"] or 0)

                if retry_count >= 3:
                    continue

                await _retry_single_job(job_id, raw_filename, media_type, retry_count)

                # Small delay between jobs to not overload
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Crop retry loop error: {e}")

        await asyncio.sleep(60)


async def _retry_single_job(job_id: str, raw_filename: str, media_type: str, retry_count: int):
    """Attempt one retry for a single pending_crop job."""
    from app.services.detector_service import get_detector_service

    detector = get_detector_service()
    if not detector.available:
        logger.warning(f"[Retry {job_id}] Detector not available, skipping")
        return

    threshold, max_area = RETRY_CONFIGS[min(retry_count, len(RETRY_CONFIGS) - 1)]
    logger.info(
        f"[Retry {job_id}] Attempt {retry_count + 1}/3: "
        f"threshold={threshold}, max_area={max_area}"
    )

    raw_path = str(Path(settings.server_data_dir) / "storage" / raw_filename)
    if not Path(raw_path).exists():
        logger.error(f"[Retry {job_id}] Raw file not found: {raw_path}")
        _mark_manual_review(job_id)
        return

    try:
        if media_type == "image":
            img = cv2.imread(raw_path)
            frames_iter = [DecodedVideoFrame(frame_index=0, timestamp_seconds=0.0, frame=img)] if img is not None else []
        else:
            frames_iter = iter_frames_from_video(raw_path, max_side=settings.frame_max_side or 960)

        # Try detection on every decoded frame sequentially
        best_crop = None
        best_detection_frame = None
        best_detection = None
        best_conf = 0.0

        for decoded in frames_iter:
            frame = decoded.frame
            dets = detector.detect(frame, conf_threshold=threshold)
            for det in dets:
                if _is_valid_tight(det, frame.shape, min_conf=threshold, max_area=max_area):
                    conf = float(getattr(det, "confidence", 0.0))
                    if conf > best_conf:
                        crop = crop_fish_best(frame, det)
                        if crop is not None and crop.size > 0:
                            best_crop = crop
                            best_detection_frame = frame
                            best_detection = det
                            best_conf = conf

        if best_crop is not None:
            logger.info(
                f"[Retry {job_id}] SUCCESS! Detection recovered with "
                f"conf={best_conf:.3f}. Re-running the complete pipeline."
            )

            if not _reset_job_for_full_pipeline(job_id, retry_count):
                logger.warning(
                    f"[Retry {job_id}] Job was not in pending_crop status. "
                    "Full pipeline reprocessing was cancelled."
                )
                return

            from app.services.job_service import process_identification_job

            recovered_candidate = {
                "frame": best_detection_frame,
                "detection": best_detection,
                "confidence": best_conf,
            }

            try:
                result = await asyncio.to_thread(
                    process_identification_job,
                    job_id,
                    force=True,
                    recovered_candidate=recovered_candidate,
                )
                logger.info(
                    f"[Retry {job_id}] Full pipeline completed successfully: "
                    f"status={result.get('status')}, "
                    f"fish_id={result.get('fish_id')}, "
                    f"sighting_id={result.get('sighting_id')}"
                )
            except Exception:
                # process_identification_job already records the job as failed.
                # Do not overwrite that state by incrementing retry_count here.
                logger.exception(
                    f"[Retry {job_id}] Full pipeline failed after "
                    "recovering the detection"
                )
            return
        else:
            # Failed this attempt
            new_count = retry_count + 1
            if new_count >= 3:
                logger.warning(f"[Retry {job_id}] All 3 retries exhausted → marking as failed")
                _mark_failed_retries(job_id)
            else:
                _increment_retry(job_id, retry_count)

    except Exception as e:
        logger.error(f"[Retry {job_id}] Error during retry: {e}")
        _increment_retry(job_id, retry_count)


def _reset_job_for_full_pipeline(job_id: str, current_count: int) -> bool:
    """
    Atomically move a pending_crop job back to uploaded so the complete
    identification pipeline can process it.

    Returns True only when exactly one pending_crop job was updated.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE identification_jobs
            SET status = 'uploaded',
                retry_count = ?,
                error_message = NULL,
                completed_at = NULL,
                preview_filename = NULL
            WHERE id = ?
              AND status = 'pending_crop'
            """,
            (current_count + 1, job_id),
        )
        updated = cursor.rowcount == 1
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        logger.exception(
            f"[Retry {job_id}] Failed to reset job for full pipeline"
        )
        return False
    finally:
        conn.close()



def _increment_retry(job_id: str, current_count: int):
    """Increment retry_count in DB."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE identification_jobs SET retry_count = ? WHERE id = ?",
            (current_count + 1, job_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"[Retry {job_id}] Failed to increment retry_count: {e}")
    finally:
        conn.close()


def _mark_failed_retries(job_id: str):
    """Mark job as failed after all retries exhausted."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE identification_jobs
               SET status = 'failed', retry_count = 3,
                   error_message = 'All automatic retries exhausted. Could not detect fish in any frame.'
               WHERE id = ?""",
            (job_id,),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"[Retry {job_id}] Failed to mark as failed: {e}")
    finally:
        conn.close()


def start_retry_service():
    """Start the background crop retry task."""
    global _retry_task
    if _retry_task is None:
        _retry_task = asyncio.create_task(_retry_pending_crops())
        logger.info("Background crop retry service registered")
