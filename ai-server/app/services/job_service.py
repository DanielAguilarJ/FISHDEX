"""
Job Service - Main orchestrator for the fish identification pipeline.

Processes identification jobs end-to-end: video download, frame extraction,
detection, classification, embedding, matching, and result persistence.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.config import settings
from app.data.czech_species import find_species_by_name
from app.services.appwrite_service import get_appwrite_service
from app.services.classifier_service import get_classifier_service
from app.services.detector_service import get_detector_service
from app.services.embedding_service import get_embedding_service
from app.services.matching_service import get_matching_service
from app.utils.video import (
    cleanup_temp_file,
    extract_frames_from_video,
    save_temp_video,
    select_best_n_frames,
)

from app.services.event_bus import event_bus
import asyncio

logger = logging.getLogger(__name__)

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

XP_BASE_MAP = {
    "common": 10,
    "uncommon": 25,
    "rare": 50,
    "legendary": 100,
}
NEW_FISH_BONUS_XP = 50


def _crop_fish_from_frame(frame: np.ndarray, detection: dict) -> np.ndarray:
    """Crop fish region from frame using OBB detection or fallback center crop."""
    h, w = frame.shape[:2]

    if detection and detection.get("bbox"):
        bbox = detection["bbox"]
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


def _generate_fish_id(area_code: str, species_slug: str, appwrite_service) -> str:
    """
    Generate fish ID in format: CZ-{area_code_clean}-{ABBREV}-{NNNN}.
    Gets next number by querying existing fish_individuals.
    """
    area_code_clean = area_code.replace("-", "").replace(" ", "").upper() if area_code else "XX"

    # Abbreviation from species slug: first 3-4 chars uppercased
    if species_slug:
        abbrev = species_slug.replace("-", "").replace("_", "")[:4].upper()
    else:
        abbrev = "UNK"

    # Query existing fish to determine next sequential number
    try:
        existing = appwrite_service.list_documents(
            database_id=settings.appwrite_database_id,
            collection_id="fish_individuals",
            queries=[
                f'startsWith("fish_id", "CZ-{area_code_clean}-{abbrev}-")',
                'limit(1)',
                'orderDesc("fish_id")',
            ],
        )
        if existing and existing.get("documents"):
            last_id = existing["documents"][0]["fish_id"]
            last_num = int(last_id.split("-")[-1])
            next_num = last_num + 1
        else:
            next_num = 1
    except Exception as e:
        logger.warning(f"Could not query existing fish for numbering: {e}")
        next_num = 1

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
    """
    Process a fish identification job end-to-end.

    Args:
        job_id: The Appwrite document ID of the identification job.
        force: If True, reprocess even if already completed.

    Returns:
        dict with keys: status, fish_id, sighting_id, species, confidence, xp_earned, is_new_fish
    """
    appwrite = get_appwrite_service()
    detector = get_detector_service()
    embedding_service = get_embedding_service()
    matching = get_matching_service()

    temp_video_path: Optional[str] = None
    job_doc: Optional[dict] = None

    try:
        # --- Step 1: Get job document ---
        _emit_progress(job_id, "processing", 5, "Job started")
        logger.info(f"[Job {job_id}] Fetching job document")
        job_doc = appwrite.get_document(
            database_id=settings.appwrite_database_id,
            collection_id="identification_jobs",
            document_id=job_id,
        )

        if not job_doc:
            raise ValueError(f"Job {job_id} not found")

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
        appwrite.update_document(
            database_id=settings.appwrite_database_id,
            collection_id="identification_jobs",
            document_id=job_id,
            data={
                "status": "processing",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "error_message": None,
            },
        )

        # --- Step 4: Download raw video ---
        raw_video_file_id = job_doc.get("raw_video_file_id")
        if not raw_video_file_id:
            raise ValueError("Job has no raw_video_file_id")

        _emit_progress(job_id, "downloading_video", 15, "Downloading video file from Appwrite Storage")
        logger.info(f"[Job {job_id}] Downloading video file: {raw_video_file_id}")
        video_bytes = appwrite.get_file_download(
            bucket_id=settings.capture_raw_videos_bucket,
            file_id=raw_video_file_id,
        )
        temp_video_path = save_temp_video(video_bytes)
        logger.info(f"[Job {job_id}] Video saved to temp: {temp_video_path}")

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
                    conf = det.get("confidence", 0.0)
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

        try:
            classifier = get_classifier_service()
            _emit_progress(job_id, "classifying_species", 70, f"Classifying species (given: {species_slug})")
            logger.info(f"[Job {job_id}] Running classifier")
            classification_result = classifier.classify(cropped_frame)

            if classification_result and classification_result.get("species"):
                classified_species = classification_result["species"]
                classification_confidence = classification_result.get("confidence", 0.0)
                logger.info(
                    f"[Job {job_id}] Classified as: {classified_species} "
                    f"(confidence: {classification_confidence:.3f})"
                )

                if not species_slug:
                    species_slug = classified_species
        except Exception as e:
            logger.warning(f"[Job {job_id}] Classifier unavailable: {e}")
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
        # Average embedding across frames for a single 2048-d vector
        if embedding.ndim > 1:
            embedding_vector = np.mean(embedding, axis=0)
        else:
            embedding_vector = embedding
        logger.info(f"[Job {job_id}] Embedding shape: {embedding_vector.shape}")

        # --- Step 11: Run matching ---
        logger.info(f"[Job {job_id}] Running matching against known fish")
        match_result = matching.find_match(
            embedding=embedding_vector,
            species_slug=species_slug,
            threshold=settings.similarity_threshold,
        )

        is_new_fish = not match_result or not match_result.get("fish_id")
        matched_fish_id = match_result.get("fish_id") if match_result else None
        match_confidence = match_result.get("confidence", 0.0) if match_result else 0.0

        logger.info(
            f"[Job {job_id}] Match result: "
            f"{'NEW FISH' if is_new_fish else f'matched {matched_fish_id}'} "
            f"(confidence: {match_confidence:.3f})"
        )

        # --- Step 12: Generate fish_id if new ---
        user_id = job_doc.get("user_id")
        area_code = job_doc.get("area_code", "XX")

        if is_new_fish:
            fish_id = _generate_fish_id(area_code, species_slug, appwrite)
            logger.info(f"[Job {job_id}] Generated new fish_id: {fish_id}")
        else:
            fish_id = matched_fish_id
            logger.info(f"[Job {job_id}] Using existing fish_id: {fish_id}")

        # --- Step 13: Upload best cropped frame ---
        _emit_progress(job_id, "uploading_results", 95, "Uploading cropped frames and saving sightings")
        logger.info(f"[Job {job_id}] Uploading cropped frame to storage")
        import cv2
        import io

        _, frame_buffer = cv2.imencode(".jpg", cropped_frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        frame_bytes = frame_buffer.tobytes()
        frame_file_id = str(uuid.uuid4())

        appwrite.upload_file(
            bucket_id=settings.capture_frames_bucket,
            file_id=frame_file_id,
            file_name=f"{job_id}_best_crop.jpg",
            file_bytes=frame_bytes,
            content_type="image/jpeg",
        )
        logger.info(f"[Job {job_id}] Uploaded frame: {frame_file_id}")

        # --- Step 14: Create fish_sightings document ---
        sighting_id = str(uuid.uuid4())
        detection_confidence = best_detection_confidence if best_detection else 0.0
        overall_confidence = (
            (detection_confidence + match_confidence) / 2.0
            if not is_new_fish
            else detection_confidence
        )
        if classification_result:
            overall_confidence = max(overall_confidence, classification_result.get("confidence", 0.0))

        xp_earned = _calculate_xp(species_info, is_new_fish)

        sighting_data = {
            "user_id": user_id,
            "fish_id": fish_id,
            "job_id": job_id,
            "species_slug": species_slug,
            "species_english": species_info.get("english_name") if species_info else None,
            "species_czech": species_info.get("czech_name") if species_info else None,
            "species_latin": species_info.get("latin_name") if species_info else None,
            "confidence": round(overall_confidence, 4),
            "is_new_fish": is_new_fish,
            "xp_earned": xp_earned,
            "area_code": area_code,
            "frame_file_id": frame_file_id,
            "raw_video_file_id": raw_video_file_id,
            "captured_at": job_doc.get("captured_at", datetime.now(timezone.utc).isoformat()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "location_lat": job_doc.get("location_lat"),
            "location_lng": job_doc.get("location_lng"),
        }

        logger.info(f"[Job {job_id}] Creating sighting document: {sighting_id}")
        appwrite.create_document(
            database_id=settings.appwrite_database_id,
            collection_id="fish_sightings",
            document_id=sighting_id,
            data=sighting_data,
        )

        # --- Step 15: Create or update fish_individuals ---
        if is_new_fish:
            logger.info(f"[Job {job_id}] Creating new fish_individuals document")
            fish_individual_data = {
                "fish_id": fish_id,
                "species_slug": species_slug,
                "species_english": species_info.get("english_name") if species_info else None,
                "species_latin": species_info.get("latin_name") if species_info else None,
                "first_seen_by": user_id,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "total_sightings": 1,
                "area_code": area_code,
                "best_frame_file_id": frame_file_id,
            }
            appwrite.create_document(
                database_id=settings.appwrite_database_id,
                collection_id="fish_individuals",
                document_id=str(uuid.uuid4()),
                data=fish_individual_data,
            )
        else:
            logger.info(f"[Job {job_id}] Updating existing fish_individuals document")
            # Find the existing document
            existing_fish = appwrite.list_documents(
                database_id=settings.appwrite_database_id,
                collection_id="fish_individuals",
                queries=[f'equal("fish_id", "{fish_id}")', "limit(1)"],
            )
            if existing_fish and existing_fish.get("documents"):
                fish_doc = existing_fish["documents"][0]
                appwrite.update_document(
                    database_id=settings.appwrite_database_id,
                    collection_id="fish_individuals",
                    document_id=fish_doc["$id"],
                    data={
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                        "total_sightings": fish_doc.get("total_sightings", 0) + 1,
                    },
                )

        # --- Step 16: Create media_files documents ---
        logger.info(f"[Job {job_id}] Creating media_files documents")
        # Video media file
        appwrite.create_document(
            database_id=settings.appwrite_database_id,
            collection_id="media_files",
            document_id=str(uuid.uuid4()),
            data={
                "user_id": user_id,
                "sighting_id": sighting_id,
                "fish_id": fish_id,
                "file_id": raw_video_file_id,
                "bucket_id": settings.capture_raw_videos_bucket,
                "media_type": "video",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        # Frame media file
        appwrite.create_document(
            database_id=settings.appwrite_database_id,
            collection_id="media_files",
            document_id=str(uuid.uuid4()),
            data={
                "user_id": user_id,
                "sighting_id": sighting_id,
                "fish_id": fish_id,
                "file_id": frame_file_id,
                "bucket_id": settings.capture_frames_bucket,
                "media_type": "frame",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # --- Step 17: Update user stats ---
        logger.info(f"[Job {job_id}] Updating user stats for user: {user_id}")
        try:
            user_stats = appwrite.list_documents(
                database_id=settings.appwrite_database_id,
                collection_id="user_stats",
                queries=[f'equal("user_id", "{user_id}")', "limit(1)"],
            )
            if user_stats and user_stats.get("documents"):
                stats_doc = user_stats["documents"][0]
                appwrite.update_document(
                    database_id=settings.appwrite_database_id,
                    collection_id="user_stats",
                    document_id=stats_doc["$id"],
                    data={
                        "total_xp": stats_doc.get("total_xp", 0) + xp_earned,
                        "total_sightings": stats_doc.get("total_sightings", 0) + 1,
                        "total_species": stats_doc.get("total_species", 0) + (1 if is_new_fish else 0),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            else:
                # Create initial stats document
                appwrite.create_document(
                    database_id=settings.appwrite_database_id,
                    collection_id="user_stats",
                    document_id=str(uuid.uuid4()),
                    data={
                        "user_id": user_id,
                        "total_xp": xp_earned,
                        "total_sightings": 1,
                        "total_species": 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except Exception as e:
            logger.error(f"[Job {job_id}] Failed to update user stats: {e}")
            # Non-fatal: don't fail the job over stats

        # --- Step 18: Store embedding in matching service ---
        logger.info(f"[Job {job_id}] Storing embedding in matching service")
        matching.store_embedding(
            fish_id=fish_id,
            embedding=embedding_vector,
            species_slug=species_slug,
            sighting_id=sighting_id,
        )

        # --- Step 19: Determine final status and update job ---
        if not species_slug and not classifier_available:
            final_status = "needs_review"
            logger.info(f"[Job {job_id}] No species identified and classifier unavailable -> needs_review")
        else:
            final_status = "completed"

        logger.info(f"[Job {job_id}] Updating job status to '{final_status}'")
        appwrite.update_document(
            database_id=settings.appwrite_database_id,
            collection_id="identification_jobs",
            document_id=job_id,
            data={
                "status": final_status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result_sighting_id": sighting_id,
                "result_fish_id": fish_id,
                "confidence": round(overall_confidence, 4),
                "species_slug": species_slug,
                "is_new_fish": is_new_fish,
                "xp_earned": xp_earned,
                "error_message": None,
            },
        )

        # --- Step 20 & 21: Cleanup and return ---
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

        # Update job to failed if we got past step 3
        if job_doc:
            try:
                appwrite.update_document(
                    database_id=settings.appwrite_database_id,
                    collection_id="identification_jobs",
                    document_id=job_id,
                    data={
                        "status": "failed",
                        "error_message": str(e)[:1000],
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as update_err:
                logger.error(
                    f"[Job {job_id}] Failed to update job status to 'failed': {update_err}"
                )

        raise

    finally:
        # --- Step 20: Always clean up temp files ---
        if temp_video_path:
            try:
                cleanup_temp_file(temp_video_path)
                logger.debug(f"[Job {job_id}] Cleaned up temp video: {temp_video_path}")
            except Exception as cleanup_err:
                logger.warning(f"[Job {job_id}] Failed to cleanup temp file: {cleanup_err}")
