"""
Job Service - Fully local database and file storage implementation of the identification pipeline.
Processes jobs locally using SQLite and writes files to the local disk.
"""

import logging
import uuid
import os
import io
import cv2
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import numpy as np

from app.config import settings
from app.database import get_db_connection
from app.data.czech_species import find_species_by_name
from app.services.classifier_service import get_classifier_service
from app.services.detector_service import get_detector_service
from app.services.embedding_service import get_embedding_service
from app.services.matching_service import get_matching_service
from app.services.event_bus import event_bus
import asyncio
from app.utils.video import (
    cleanup_temp_file,
    extract_frames_from_video,
    select_best_n_frames,
)

logger = logging.getLogger(__name__)

XP_BASE_MAP = {
    "common": 10,
    "uncommon": 25,
    "rare": 50,
    "legendary": 100,
}
NEW_FISH_BONUS_XP = 50

def _emit_progress(job_id: str, status: str, progress: int, message: str):
    payload = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(event_bus.emit("job_progress", payload))
        )
    except RuntimeError:
        pass

def _get_detection_confidence(detection) -> float:
    if detection is None:
        return 0.0

    if isinstance(detection, dict):
        return float(detection.get("confidence", 0.0) or 0.0)

    return float(getattr(detection, "confidence", 0.0) or 0.0)


def _get_detection_bbox(detection):
    if detection is None:
        return None

    if isinstance(detection, dict):
        return detection.get("bbox") or detection.get("bbox_xyxy")

    return getattr(detection, "bbox_xyxy", None)


def _crop_fish_from_frame(frame: np.ndarray, detection) -> np.ndarray:
    """Crop fish region from frame using detection or fallback center crop."""
    h, w = frame.shape[:2]

    bbox = _get_detection_bbox(detection)

    if bbox:
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))

        if x2 > x1 and y2 > y1:
            return frame[y1:y2, x1:x2]

    # Fallback: center crop (60% of frame)
    crop_ratio = 0.6
    cx, cy = w // 2, h // 2
    cw, ch = int(w * crop_ratio) // 2, int(h * crop_ratio) // 2
    x1 = max(0, cx - cw)
    y1 = max(0, cy - ch)
    x2 = min(w, cx + cw)
    y2 = min(h, cy + ch)
    return frame[y1:y2, x1:x2]

def _generate_fish_id(area_code: str, species_slug: str) -> str:
    """Generate fish ID in format: CZ-{area_code_clean}-{ABBREV}-{NNNN} using local SQLite."""
    area_code_clean = area_code.replace("-", "").replace(" ", "").upper() if area_code else "XX"

    if species_slug:
        abbrev = species_slug.replace("-", "").replace("_", "")[:4].upper()
    else:
        abbrev = "UNK"

    conn = get_db_connection()
    cursor = conn.cursor()
    
    next_num = 1
    try:
        prefix = f"CZ-{area_code_clean}-{abbrev}-%"
        cursor.execute(
            "SELECT fish_id FROM fish_individuals WHERE fish_id LIKE ? ORDER BY fish_id DESC LIMIT 1",
            (prefix,)
        )
        row = cursor.fetchone()
        if row:
            last_id = row["fish_id"]
            last_num = int(last_id.split("-")[-1])
            next_num = last_num + 1
    except Exception as e:
        logger.warning(f"Could not query existing fish for numbering: {e}")
    finally:
        conn.close()

    return f"CZ-{area_code_clean}-{abbrev}-{next_num:04d}"

def _calculate_xp(species_info: Optional[dict], is_new_fish: bool) -> int:
    """Calculate XP earned for this sighting."""
    base_xp = 10  # default for unknown
    if species_info:
        rarity = species_info.get("rarity", "common")
        base_xp = species_info.get("xp_base", XP_BASE_MAP.get(rarity, 10))

    total_xp = base_xp
    if is_new_fish:
        total_xp += NEW_FISH_BONUS_XP

    return total_xp

def process_identification_job(job_id: str, force: bool = False) -> dict:
    """Process a fish identification job locally using SQLite database."""
    detector = get_detector_service()
    embedding_service = get_embedding_service()
    matching = get_matching_service()

    temp_video_path: Optional[str] = None
    job_doc: Optional[dict] = None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # --- Step 1: Get job document ---
        _emit_progress(job_id, "processing", 5, "Job started")
        logger.info(f"[Job {job_id}] Fetching job from local database")
        
        cursor.execute("SELECT * FROM identification_jobs WHERE id = ?", (job_id,))
        job_row = cursor.fetchone()
        
        if not job_row:
            raise ValueError(f"Job {job_id} not found in database")
            
        job_doc = dict(job_row)

        # --- Step 2: Validate status ---
        current_status = job_doc.get("status")
        logger.info(f"[Job {job_id}] Current status: {current_status}")

        if current_status != "uploaded" and not force:
            if current_status == "completed":
                raise ValueError(f"Job {job_id} already completed. Use force=True to reprocess.")
            elif current_status == "processing":
                raise ValueError(f"Job {job_id} is already being processed.")
            elif current_status == "failed" and not force:
                raise ValueError(f"Job {job_id} previously failed. Use force=True to retry.")

        # --- Step 3: Update status to processing ---
        logger.info(f"[Job {job_id}] Setting status to 'processing'")
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE identification_jobs SET status = 'processing', started_at = ?, error_message = NULL WHERE id = ?",
            (now_str, job_id)
        )
        conn.commit()

        # --- Step 4: Locate raw video ---
        raw_video_filename = job_doc.get("raw_video_filename")
        if not raw_video_filename:
            raise ValueError("Job has no raw_video_filename")

        _emit_progress(job_id, "downloading_video", 15, "Loading video file from local storage")
        temp_video_path = str(Path(settings.server_data_dir) / "storage" / raw_video_filename)
        logger.info(f"[Job {job_id}] Video resolved to local path: {temp_video_path}")
        
        if not os.path.exists(temp_video_path):
            raise FileNotFoundError(f"Raw video file not found on disk: {temp_video_path}")

        # --- Step 5: Extract frames ---
        _emit_progress(job_id, "extracting_frames", 30, "Extracting and selecting video frames")
        logger.info(f"[Job {job_id}] Extracting frames (max {settings.max_frames_to_extract})")
        all_frames = extract_frames_from_video(
            temp_video_path,
            max_frames=settings.max_frames_to_extract or 10,
        )
        if not all_frames or len(all_frames) == 0:
            raise ValueError("No frames could be extracted from video")
        logger.info(f"[Job {job_id}] Extracted {len(all_frames)} frames")

        # --- Step 6: Select best frames ---
        max_save = settings.max_frames_to_save or 5
        best_frames = select_best_n_frames(all_frames, n=max_save)
        logger.info(f"[Job {job_id}] Selected {len(best_frames)} best frames")

        # --- Step 7: Run detector on each frame ---
        _emit_progress(job_id, "detecting_fish", 50, "Running YOLOv8 OBB fish detector")
        logger.info(f"[Job {job_id}] Running fish detection")
        best_detection = None
        best_detection_frame = None
        best_detection_confidence = 0.0

        for i, frame in enumerate(best_frames):
            detections = detector.detect(frame)
            if detections:
                for det in detections:
                    conf = _get_detection_confidence(det)
                    if conf > best_detection_confidence:
                        best_detection_confidence = conf
                        best_detection = det
                        best_detection_frame = frame

        if best_detection_frame is None:
            logger.warning(f"[Job {job_id}] No fish detected, using best frame with center crop")
            best_detection_frame = best_frames[0]

        logger.info(
            f"[Job {job_id}] Best detection confidence: {best_detection_confidence:.3f}"
        )

        # --- Step 8: Crop fish from frame ---
        logger.info(f"[Job {job_id}] Cropping fish from frame")
        cropped_frame = _crop_fish_from_frame(best_detection_frame, best_detection)

        # Also crop additional frames for embedding
        cropped_frames = [cropped_frame]
        for frame in best_frames:
            if frame is not best_detection_frame:
                cropped = _crop_fish_from_frame(frame, best_detection)
                cropped_frames.append(cropped)
                if len(cropped_frames) >= max_save:
                    break

        # --- Step 9: Run classifier ---
        species_slug = job_doc.get("species_slug")
        species_info = None
        classification_result = None
        classifier_available = True
        classification_confidence = 0.0

        try:
            classifier = get_classifier_service()
            _emit_progress(
                job_id,
                "classifying_species",
                70,
                f"Classifying species (given: {species_slug})",
            )
            logger.info(f"[Job {job_id}] Running classifier")
            classification_result = classifier.classify(cropped_frame)

            if not classification_result or not classification_result.get("available", False):
                classifier_available = False
                logger.warning(f"[Job {job_id}] Classifier unavailable or returned no predictions")
            else:
                predictions = classification_result.get("predictions") or []
                if predictions:
                    top_prediction = predictions[0]
                    classified_species = (
                        top_prediction.get("species_slug")
                        or top_prediction.get("species")
                    )
                    classification_confidence = float(
                        top_prediction.get("confidence", 0.0) or 0.0
                    )

                    logger.info(
                        f"[Job {job_id}] Classified as: {classified_species} "
                        f"(confidence: {classification_confidence:.3f})"
                    )

                    if not species_slug and classified_species:
                        species_slug = classified_species
        except Exception as e:
            logger.warning(f"[Job {job_id}] Classifier failed: {e}")
            classifier_available = False

        # Look up species in catalog
        if species_slug:
            species_info = find_species_by_name(species_slug)
            if species_info:
                logger.info(
                    f"[Job {job_id}] Species info: {species_info.get('english_name')} "
                    f"({species_info.get('rarity')})"
                )

        # --- Step 10: Generate embedding ---
        _emit_progress(job_id, "matching_individual", 85, "Generating embeddings and matching features")
        logger.info(f"[Job {job_id}] Generating embeddings from {len(cropped_frames)} crops")
        embedding = embedding_service.extract_embeddings(cropped_frames)
        if embedding.ndim > 1:
            embedding_vector = np.mean(embedding, axis=0)
        else:
            embedding_vector = embedding
        logger.info(f"[Job {job_id}] Embedding shape: {embedding_vector.shape}")

        # --- Step 11: Run matching ---
        logger.info(f"[Job {job_id}] Running matching against known fish")
        if species_slug:
            matched_fish_id, match_confidence = matching.find_match(
                embedding=embedding_vector,
                species_slug=species_slug,
                area_code=job_doc.get("area_code"),
                threshold=settings.similarity_threshold,
            )
        else:
            matched_fish_id, match_confidence = None, 0.0

        is_new_fish = matched_fish_id is None

        logger.info(
            f"[Job {job_id}] Match result: "
            f"{'NEW FISH' if is_new_fish else f'matched {matched_fish_id}'} "
            f"(confidence: {match_confidence:.3f})"
        )

        # --- Step 12: Generate fish_id if new ---
        user_id = job_doc.get("user_id")
        area_code = job_doc.get("area_code", "XX")

        if is_new_fish:
            fish_id = _generate_fish_id(area_code, species_slug)
            logger.info(f"[Job {job_id}] Generated new fish_id: {fish_id}")
        else:
            fish_id = matched_fish_id
            logger.info(f"[Job {job_id}] Using existing fish_id: {fish_id}")

        # --- Step 13: Save best cropped frame locally ---
        _emit_progress(job_id, "uploading_results", 95, "Uploading cropped frames and saving sightings")
        logger.info(f"[Job {job_id}] Saving cropped frame locally")

        # Encode cropped frame to JPEG
        _, frame_buffer = cv2.imencode(".jpg", cropped_frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality or 90])
        frame_bytes = frame_buffer.tobytes()
        
        # Save cropped frame under data/storage/cropped_frames/
        frame_file_id = str(uuid.uuid4())
        frame_filename = f"cropped_frames/{frame_file_id}.jpg"
        local_crop_path = Path(settings.server_data_dir) / "storage" / frame_filename
        local_crop_path.parent.mkdir(parents=True, exist_ok=True)
        local_crop_path.write_bytes(frame_bytes)
        
        logger.info(f"[Job {job_id}] Cropped frame saved to disk: {local_crop_path}")

        # --- Step 14: Create fish_sightings record ---
        sighting_id = str(uuid.uuid4())
        detection_confidence = best_detection_confidence if best_detection else 0.0
        overall_confidence = (
            (detection_confidence + match_confidence) / 2.0
            if not is_new_fish
            else detection_confidence
        )
        if classification_confidence > 0:
            overall_confidence = max(overall_confidence, classification_confidence)

        xp_earned = _calculate_xp(species_info, is_new_fish)

        cursor.execute(
            """INSERT INTO fish_sightings (
                id, user_id, fish_id, job_id, species_slug, species_english, species_czech, species_latin, 
                confidence, is_new_fish, xp_earned, area_code, frame_filename, raw_video_filename, 
                captured_at, created_at, location_lat, location_lng
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sighting_id, user_id, fish_id, job_id, species_slug,
                species_info.get("english_name") if species_info else None,
                species_info.get("czech_name") if species_info else None,
                species_info.get("latin_name") if species_info else None,
                round(overall_confidence, 4), 1 if is_new_fish else 0, xp_earned, area_code,
                frame_filename, raw_video_filename,
                job_doc.get("created_at", now_str), now_str,
                job_doc.get("latitude"), job_doc.get("longitude")
            )
        )

        # --- Step 15: Create or update fish_individuals ---
        if is_new_fish:
            logger.info(f"[Job {job_id}] Creating new fish_individuals record")
            cursor.execute(
                """INSERT INTO fish_individuals (
                    id, fish_id, species_slug, species_english, species_latin, 
                    first_seen_by, first_seen_at, last_seen_at, total_sightings, area_code, best_frame_filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    str(uuid.uuid4()), fish_id, species_slug,
                    species_info.get("english_name") if species_info else None,
                    species_info.get("latin_name") if species_info else None,
                    user_id, now_str, now_str, area_code, frame_filename
                )
            )
        else:
            logger.info(f"[Job {job_id}] Updating existing fish_individuals record")
            cursor.execute(
                """UPDATE fish_individuals 
                   SET last_seen_at = ?, total_sightings = total_sightings + 1 
                   WHERE fish_id = ?""",
                (now_str, fish_id)
            )

        # --- Step 17: Update user stats ---
        logger.info(f"[Job {job_id}] Updating user stats locally for user: {user_id}")
        cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
        stats_row = cursor.fetchone()
        
        if stats_row:
            cursor.execute(
                """UPDATE user_stats 
                   SET total_xp = total_xp + ?, total_sightings = total_sightings + 1, 
                       total_species = total_species + ?, updated_at = ?
                   WHERE user_id = ?""",
                (xp_earned, 1 if is_new_fish else 0, now_str, user_id)
            )
        else:
            cursor.execute(
                """INSERT INTO user_stats (id, user_id, total_xp, total_sightings, total_species, updated_at) 
                   VALUES (?, ?, ?, 1, 1, ?)""",
                (str(uuid.uuid4()), user_id, xp_earned, now_str)
            )

        # --- Step 18: Store embedding in matching service ---
        logger.info(f"[Job {job_id}] Storing embedding in matching service")
        if species_slug:
            matching.store_embedding(
                fish_id=fish_id,
                embedding=embedding_vector,
                species_slug=species_slug,
                area_code=area_code,
                sighting_id=sighting_id,
            )
        else:
            logger.info(f"[Job {job_id}] Skipping embedding storage because species_slug is missing")

        # --- Step 19: Determine final status and update job ---
        if not species_slug:
            final_status = "needs_review"
            logger.info(f"[Job {job_id}] No species identified -> needs_review")
        else:
            final_status = "completed"

        logger.info(f"[Job {job_id}] Updating job status to '{final_status}'")
        cursor.execute(
            """UPDATE identification_jobs 
               SET status = ?, completed_at = ?, result_sighting_id = ?, result_fish_id = ?, 
                   confidence = ?, species_slug = ?, is_new_fish = ?, xp_earned = ?, error_message = NULL
               WHERE id = ?""",
            (
                final_status, now_str, sighting_id, fish_id,
                round(overall_confidence, 4), species_slug, 1 if is_new_fish else 0, xp_earned, job_id
            )
        )
        conn.commit()

        # --- Step 20 & 21: Return results ---
        result = {
            "status": final_status,
            "job_id": job_id,
            "fish_id": fish_id,
            "sighting_id": sighting_id,
            "species_slug": species_slug,
            "species_english": species_info.get("english_name") if species_info else None,
            "confidence": round(overall_confidence, 4),
            "is_new_fish": is_new_fish,
            "xp_earned": xp_earned,
            "detection_confidence": round(detection_confidence, 4),
            "match_confidence": round(match_confidence, 4),
        }

        _emit_progress(job_id, final_status, 100, f"Job completed successfully: {fish_id}")
        logger.info(f"[Job {job_id}] Processing complete: {result}")
        return result

    except Exception as e:
        _emit_progress(job_id, "failed", 100, f"Failed: {str(e)[:100]}")
        logger.error(f"[Job {job_id}] Processing failed: {e}", exc_info=True)
        
        # Update job to failed in database
        try:
            cursor.execute(
                """UPDATE identification_jobs 
                   SET status = 'failed', error_message = ?, completed_at = ? 
                   WHERE id = ?""",
                (str(e)[:1000], datetime.now(timezone.utc).isoformat(), job_id)
            )
            conn.commit()
        except Exception as update_err:
            logger.error(f"[Job {job_id}] Failed to save job failure state: {update_err}")

        raise
    finally:
        conn.close()
