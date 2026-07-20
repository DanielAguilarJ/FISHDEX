import logging
import uuid
import os
import io
import cv2
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import numpy as np

from app.config import settings
from app.database import get_db_connection
from app.data.czech_species import find_species_by_name
from app.services.classifier_service import get_classifier_service
from app.services.detector_service import get_detector_service
from app.services.reid_embedding_service import get_reid_embedding_service
from app.services.matching_service import get_matching_service
from app.services.identification_pipeline import (
    get_identification_pipeline,
    CaptureMetadata,
)
from app.services.fish_tracking_service import validate_single_fish
from app.services.capture_quality_service import evaluate_capture
from app.services.event_bus import event_bus
from app.services.artifact_service import (
    save_job_artifacts,
    save_fish_capture_artifacts,
    update_fish_index_file,
)
import asyncio
from app.utils.video import (
    cleanup_temp_file,
    extract_frames_from_video,
    select_best_n_frames,
)
from app.utils.area_utils import normalize_area_code
from app.utils.crop_utils import crop_fish_best, crop_bbox_aligned_strict, crop_bbox_preserve_frame_aspect

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


def _crop_fish_from_frame(frame: np.ndarray, detection) -> Optional[np.ndarray]:
    """
    Primary crop: OBB-rotated tight crop using the detected width, height and
    rotation from the model. Falls back to axis-aligned bbox if OBB fails.
    Returns None if no valid crop possible (no frame fallback!).
    """
    result = crop_fish_best(frame, detection, pad_frac=settings.crop_padding_frac)
    if result is None or result.size == 0:
        result = crop_bbox_aligned_strict(frame, detection, pad_frac=settings.crop_padding_frac)
    return result


def _detection_area_ratio(detection, frame_shape) -> float:
    """Return ratio of OBB area to frame area (0.0–1.0)."""
    polygon = None
    if detection is not None:
        if isinstance(detection, dict):
            polygon = detection.get("polygon")
        else:
            polygon = getattr(detection, "polygon", None)

    if not polygon or len(polygon) < 4:
        return 1.0

    h, w = frame_shape[:2]
    frame_area = float(h * w)
    if frame_area <= 0:
        return 1.0

    pts = np.array([[p[0], p[1]] for p in polygon[:4]], dtype=np.float32)
    obb_area = abs(float(cv2.contourArea(pts)))
    return obb_area / frame_area


def _is_valid_tight_detection(detection, frame_shape, min_conf: float = 0.30) -> bool:
    """
    Return True only if detection is a REAL tight fish detection.
    Rejects: fallbacks, too-large OBBs, too-small OBBs, low confidence.
    """
    conf = _get_detection_confidence(detection)
    if conf < min_conf:
        return False

    polygon = None
    bbox = None
    if detection is not None:
        if isinstance(detection, dict):
            polygon = detection.get("polygon")
            bbox = detection.get("bbox_xyxy") or detection.get("bbox")
        else:
            polygon = getattr(detection, "polygon", None)
            bbox = getattr(detection, "bbox_xyxy", None)

    if not polygon or len(polygon) < 4:
        return False

    # Area ratio check
    ratio = _detection_area_ratio(detection, frame_shape)
    if ratio < 0.001:
        return False  # Too tiny = noise
    if ratio > 0.65:
        return False  # Too large = fallback or bad detection

    # Minimum bbox size (8x8 px)
    if bbox and len(bbox) >= 4:
        bw = float(bbox[2]) - float(bbox[0])
        bh = float(bbox[3]) - float(bbox[1])
        if bw < 8 or bh < 8:
            return False

    return True


def _sharpness_score(frame: np.ndarray) -> float:
    """Laplacian variance as sharpness metric."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _candidate_score(frame: np.ndarray, detection) -> float:
    """Combined quality score: 70% confidence + 20% sharpness + 10% tightness."""
    conf = _get_detection_confidence(detection)
    sharp = min(_sharpness_score(frame) / 500.0, 1.0)
    area_ratio = _detection_area_ratio(detection, frame.shape)
    # Penalize large boxes
    area_quality = 1.0 - min(max(area_ratio - 0.35, 0.0) / 0.30, 1.0)
    return (0.70 * conf) + (0.20 * sharp) + (0.10 * area_quality)

def _infer_media_type(filename: str | None, content_type: str | None = None) -> str:
    content_type = (content_type or "").lower()
    filename = (filename or "").lower()

    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"

    if filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "image"

    return "video"


def _load_frames_from_media(path: str, media_type: str) -> list[np.ndarray]:
    if media_type == "image":
        img = cv2.imread(path)
        if img is None:
            raise ValueError(f"Could not read image file: {path}")
        return [img]

    return extract_frames_from_video(
        path,
        max_frames=settings.max_frames_to_extract or 10,
        max_side=settings.frame_max_side or 960,
    )

def _generate_fish_id(cursor, area_code: str, species_slug: str) -> str:
    """Generate fish ID in format: CZ-{area_code_clean}-{ABBREV}-{NNNN} using local SQLite cursor."""
    area_code_clean = normalize_area_code(area_code)

    if species_slug:
        abbrev = species_slug.replace("-", "").replace("_", "")[:4].upper()
    else:
        abbrev = "UNK"

    next_num = 1
    prefix = f"CZ-{area_code_clean}-{abbrev}-%"
    cursor.execute(
        "SELECT fish_id FROM fish_individuals WHERE fish_id LIKE ? ORDER BY fish_id DESC LIMIT 1",
        (prefix,)
    )
    row = cursor.fetchone()
    if row:
        last_id = row["fish_id"]
        try:
            last_num = int(last_id.split("-")[-1])
            next_num = last_num + 1
        except Exception:
            pass

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

def process_identification_job(
    job_id: str,
    force: bool = False,
    recovered_candidate: Optional[dict] = None,
) -> dict:
    """
    Process a fish identification job locally using SQLite database.

    recovered_candidate is used only by the background crop retry service.
    When provided, it must contain:
      - frame: numpy.ndarray
      - detection: detector result object
      - confidence: float

    The recovered detection is injected into the normal pipeline so the job
    still generates embeddings, performs matching, creates the sighting and
    stores all final artifacts.
    """
    detector = get_detector_service()
    embedding_service = get_reid_embedding_service()   # FishEncoder 512-d (trained for re-ID)
    matching = get_matching_service()

    temp_video_path: Optional[str] = None
    job_doc: Optional[dict] = None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # --- Step 0: Phase 1 Idempotency Check ---
        cursor.execute("SELECT * FROM fish_sightings WHERE job_id = ? LIMIT 1", (job_id,))
        existing_sighting = cursor.fetchone()
        if existing_sighting and not force:
            logger.info(f"[Job {job_id}] Sighting already exists in DB (Phase 1). Skipping processing.")
            sighting_data = dict(existing_sighting)
            
            # Canonicalize species slug info if possible
            species_slug = sighting_data.get("species_slug")
            species_info = find_species_by_name(species_slug) if species_slug else None
            
            result = {
                "status": "completed" if species_slug else "needs_review",
                "job_id": job_id,
                "fish_id": sighting_data.get("fish_id"),
                "sighting_id": sighting_data.get("id"),
                "species_slug": species_slug,
                "species_english": species_info.get("english_name") if species_info else None,
                "confidence": sighting_data.get("confidence", 0.0),
                "is_new_fish": bool(sighting_data.get("is_new_fish")),
                "xp_earned": sighting_data.get("xp_earned", 10),
                "detection_confidence": sighting_data.get("detection_confidence", 0.0),
                "classification_confidence": sighting_data.get("classification_confidence", 0.0),
                "match_confidence": sighting_data.get("match_confidence", 0.0),
            }
            _emit_progress(job_id, result["status"], 100, f"Job skipped (already done): {sighting_data.get('fish_id')}")
            return result

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

        if current_status != "uploaded" and current_status != "pending_crop" and not force:
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

        # --- Step 4: Locate raw media (video/photo) ---
        raw_video_filename = job_doc.get("raw_media_filename") or job_doc.get("raw_video_filename")
        if not raw_video_filename:
            raise ValueError("Job has no raw media filename")

        media_type = job_doc.get("media_type") or _infer_media_type(
            raw_video_filename,
            job_doc.get("content_type")
        )

        _emit_progress(job_id, "downloading_video", 15, f"Loading {media_type} file from local storage")
        temp_video_path = str(Path(settings.server_data_dir) / "storage" / raw_video_filename)
        logger.info(f"[Job {job_id}] Media resolved to local path: {temp_video_path} (type: {media_type})")
        
        if not os.path.exists(temp_video_path):
            raise FileNotFoundError(f"Raw media file not found on disk: {temp_video_path}")

        # --- Step 5: Extract frames ---
        _emit_progress(job_id, "extracting_frames", 30, f"Extracting frames from {media_type}")
        all_frames = _load_frames_from_media(temp_video_path, media_type)
        if not all_frames or len(all_frames) == 0:
            raise ValueError(f"No frames could be loaded from {media_type}")
        logger.info(f"[Job {job_id}] Loaded {len(all_frames)} frames")

        # --- Step 6: Select best frames ---
        max_save = settings.max_frames_to_save or 5
        best_frames = select_best_n_frames(all_frames, n=max_save)
        logger.info(f"[Job {job_id}] Selected {len(best_frames)} best frames")

        # --- Step 7: Detect fish — with validation + retries ---
        _emit_progress(job_id, "detecting_fish", 50, "Running YOLOv8 OBB fish detector")
        logger.info(f"[Job {job_id}] Running fish detection with candidate scoring")

        # Collect valid tight detections from best frames.
        # A detection recovered by retry_service is injected directly into
        # this list so the complete identification pipeline can continue.
        valid_candidates: list[tuple] = []  # (score, frame, det, conf)
        base_threshold = settings.detector_confidence_threshold or 0.30

        if recovered_candidate is not None:
            recovered_frame = recovered_candidate.get("frame")
            recovered_detection = recovered_candidate.get("detection")
            recovered_confidence = float(
                recovered_candidate.get("confidence", 0.0) or 0.0
            )

            if (
                not isinstance(recovered_frame, np.ndarray)
                or recovered_frame.size == 0
            ):
                raise ValueError(
                    "Recovered retry candidate does not contain a valid frame"
                )

            if recovered_detection is None:
                raise ValueError(
                    "Recovered retry candidate does not contain a detection"
                )

            recovered_score = _candidate_score(
                recovered_frame,
                recovered_detection,
            )
            valid_candidates.append(
                (
                    recovered_score,
                    recovered_frame,
                    recovered_detection,
                    recovered_confidence,
                )
            )

            logger.info(
                f"[Job {job_id}] Using detection recovered by retry service: "
                f"score={recovered_score:.3f}, "
                f"confidence={recovered_confidence:.3f}"
            )
        else:
            for frame in best_frames:
                detections = detector.detect(
                    frame,
                    conf_threshold=base_threshold,
                )
                for det in detections:
                    if _is_valid_tight_detection(
                        det,
                        frame.shape,
                        min_conf=base_threshold,
                    ):
                        score = _candidate_score(frame, det)
                        conf = _get_detection_confidence(det)
                        valid_candidates.append(
                            (score, frame, det, conf)
                        )

            # Retry with lowered thresholds if no valid candidates were found.
            if not valid_candidates:
                retry_thresholds = [0.25, 0.20]
                for retry_idx, retry_thresh in enumerate(
                    retry_thresholds,
                    start=1,
                ):
                    logger.info(
                        f"[Job {job_id}] Detection retry {retry_idx}: "
                        f"threshold={retry_thresh}"
                    )
                    for frame in all_frames:
                        detections = detector.detect(
                            frame,
                            conf_threshold=retry_thresh,
                        )
                        for det in detections:
                            if _is_valid_tight_detection(
                                det,
                                frame.shape,
                                min_conf=retry_thresh,
                            ):
                                score = _candidate_score(frame, det)
                                conf = _get_detection_confidence(det)
                                valid_candidates.append(
                                    (score, frame, det, conf)
                                )
                    if valid_candidates:
                        logger.info(
                            f"[Job {job_id}] Retry {retry_idx} found "
                            f"{len(valid_candidates)} candidates"
                        )
                        break

        # If STILL no valid candidates → mark as pending_crop
        if not valid_candidates:
            logger.warning(f"[Job {job_id}] No valid tight detection after 3 attempts. Marking pending_crop.")
            _emit_progress(job_id, "pending_crop", 100, "No tight fish detection found; queued for retry")

            # Save raw and frames only (no fake crops)
            job_artifacts = save_job_artifacts(
                job_id=job_id,
                selected_frames=best_frames,
                cropped_frames=[],
                raw_video_path=temp_video_path,
            )

            # Strict mode: do NOT expose the raw frame as preview.
            # selected_frames are kept as internal artefacts for debugging/retry.
            temp_preview = None

            cursor.execute(
                """UPDATE identification_jobs
                   SET status = 'pending_crop', error_message = ?,
                       preview_filename = ?, artifact_dir = ?, completed_at = ?
                   WHERE id = ?""",
                (
                    "No valid tight fish detection found after 3 attempts. Queued for background retry.",
                    temp_preview,
                    job_artifacts.get("job_artifact_dir"),
                    datetime.now(timezone.utc).isoformat(),
                    job_id,
                ),
            )
            conn.commit()

            return {
                "status": "pending_crop",
                "job_id": job_id,
                "reason": "no_valid_tight_detection",
                "preview_filename": temp_preview,
            }

        # Sort by combined score (best first)
        valid_candidates.sort(key=lambda x: x[0], reverse=True)

        best_score, best_detection_frame, best_detection, best_detection_confidence = valid_candidates[0]
        logger.info(
            f"[Job {job_id}] Best candidate: score={best_score:.3f} "
            f"confidence={best_detection_confidence:.3f} "
            f"area_ratio={_detection_area_ratio(best_detection, best_detection_frame.shape):.2f}"
        )

        # --- Step 7b: Dataset pass — collect ALL valid detections from all frames ---
        dataset_frame_detections: list[tuple] = []  # (frame, detection, conf)

        if recovered_candidate is not None:
            dataset_frame_detections.append(
                (
                    best_detection_frame,
                    best_detection,
                    best_detection_confidence,
                )
            )

        logger.info(f"[Job {job_id}] Dataset pass: scanning {len(all_frames)} frames")
        for d_frame in all_frames:
            d_dets = detector.detect(d_frame, conf_threshold=base_threshold)
            for d_det in d_dets:
                if _is_valid_tight_detection(d_det, d_frame.shape, min_conf=base_threshold):
                    d_conf = _get_detection_confidence(d_det)
                    dataset_frame_detections.append((d_frame, d_det, d_conf))
                    break  # One detection per frame for dataset
        logger.info(
            f"[Job {job_id}] Dataset pass: {len(dataset_frame_detections)}"
            f"/{len(all_frames)} frames with valid tight detections"
        )

        # --- Step 8: Crop fish — OBB-rotated (primary) + axis-aligned bbox (secondary) ---
        logger.info(f"[Job {job_id}] Cropping fish: OBB-rotated (primary) + axis-aligned bbox (secondary)")

        # Primary crop: OBB-rotated tight crop.
        # Uses the detected width, height and rotation from the model.
        cropped_frame = crop_fish_best(
            best_detection_frame,
            best_detection,
            pad_frac=settings.crop_padding_frac,
        )

        # Secondary crop: axis-aligned bbox, only for dataset/debug diversity.
        cropped_frame_bbox = crop_bbox_aligned_strict(
            best_detection_frame,
            best_detection,
            pad_frac=settings.crop_padding_frac,
        )

        # Safety: if the OBB crop fails, fall back to bbox as primary.
        # If that also fails, mark the job as pending_crop.
        if cropped_frame is None or cropped_frame.size == 0:
            logger.warning(
                "[Job %s] crop_fish_best returned None for best candidate. "
                "Attempting bbox fallback.",
                job_id,
            )
            cropped_frame = cropped_frame_bbox
            cropped_frame_bbox = None

        if cropped_frame is None or cropped_frame.size == 0:
            logger.warning(
                "[Job %s] Both OBB and bbox crop returned None. "
                "Marking pending_crop (strict mode — no frame fallback).",
                job_id,
            )
            _emit_progress(
                job_id,
                "pending_crop",
                100,
                "Fish detected but no valid crop could be produced",
            )

            job_artifacts = save_job_artifacts(
                job_id=job_id,
                selected_frames=best_frames,
                cropped_frames=[],
                raw_video_path=temp_video_path,
            )

            cursor.execute(
                """UPDATE identification_jobs
                   SET status = 'pending_crop', error_message = ?,
                       preview_filename = ?, artifact_dir = ?, completed_at = ?
                   WHERE id = ?""",
                (
                    "Fish detected but both OBB and bbox crop returned no valid output.",
                    None,  # strict: no frame-complete preview exposed
                    job_artifacts.get("job_artifact_dir"),
                    datetime.now(timezone.utc).isoformat(),
                    job_id,
                ),
            )
            conn.commit()

            return {
                "status": "pending_crop",
                "job_id": job_id,
                "reason": "obb_and_bbox_crop_failed_after_detection",
                "preview_filename": None,
            }

        cropped_frames = [cropped_frame]
        cropped_frames_bbox = [cropped_frame_bbox] if cropped_frame_bbox is not None else []

        # Additional crops from other valid candidates
        for _, frame, det, _ in valid_candidates[1:]:
            if len(cropped_frames) >= max_save:
                break
            crop = crop_fish_best(frame, det, pad_frac=settings.crop_padding_frac)
            if crop is not None:
                cropped_frames.append(crop)

                bbox_crop = crop_bbox_aligned_strict(
                    frame,
                    det,
                    pad_frac=settings.crop_padding_frac,
                )
                if bbox_crop is not None:
                    cropped_frames_bbox.append(bbox_crop)

        logger.info(
            f"[Job {job_id}] Produced {len(cropped_frames)} OBB-rotated crops "
            f"+ {len(cropped_frames_bbox)} axis-aligned bbox crops"
        )

        # --- Step 9: Resolve and validate the user-selected species ---
        species_slug_raw = job_doc.get("species_slug")
        species_info = None
        classification_result = None
        classifier_available = False
        classification_confidence = 0.0

        logger.info(
            f"[Job {job_id}] Bypassing species classification per "
            "binary detection configuration."
        )

        if (
            not isinstance(species_slug_raw, str)
            or not species_slug_raw.strip()
        ):
            raise ValueError(
                "Job cannot be identified without a selected species_slug"
            )

        species_info = find_species_by_name(species_slug_raw.strip())
        if species_info is None:
            raise ValueError(
                f"Job contains an invalid species_slug: {species_slug_raw}"
            )

        # Always use the canonical catalog slug for matching, storage and UI.
        species_slug = species_info["slug"]

        logger.info(
            f"[Job {job_id}] Species info: "
            f"{species_info.get('english_name')} / "
            f"{species_info.get('latin_name')} "
            f"slug={species_slug} "
            f"rarity={species_info.get('rarity')}"
        )

        # --- Step 10: Tracking + Quality assessment ---
        _emit_progress(job_id, "analyzing_quality", 75, "Assessing capture quality and tracking")

        # Build per-frame detection list for tracking
        frame_detections_for_tracking: list[list[dict]] = []
        detection_dicts_for_quality: list[dict] = []

        for d_frame, d_det, d_conf in dataset_frame_detections:
            bbox = _get_detection_bbox(d_det)
            if bbox and len(bbox) >= 4:
                det_dict = {
                    "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                    "confidence": float(d_conf),
                    "frame_height": d_frame.shape[0],
                    "frame_width": d_frame.shape[1],
                }
                frame_detections_for_tracking.append([det_dict])
                detection_dicts_for_quality.append(det_dict)
            else:
                frame_detections_for_tracking.append([])

        # Run tracking to verify single fish
        tracking_result = validate_single_fish(frame_detections_for_tracking)
        track_consistent = tracking_result.is_single_fish
        multiple_fish_detected = tracking_result.multiple_fish_detected

        # Assess capture quality
        quality_result = evaluate_capture(
            cropped_frames=cropped_frames,
            detections=detection_dicts_for_quality[:len(cropped_frames)],
        )
        quality_score = quality_result.overall_score

        logger.info(
            f"[Job {job_id}] Tracking: consistent={track_consistent}, "
            f"multiple_fish={multiple_fish_detected}. "
            f"Quality: score={quality_score:.3f}"
        )

        # --- Step 11: Generate per-frame embedding matrix ---
        _emit_progress(job_id, "matching_individual", 85, "Generating FishEncoder embeddings")
        logger.info(f"[Job {job_id}] Generating per-frame embeddings from {len(cropped_frames)} crops")

        # extract_embedding_matrix returns (N, 512) L2-normalised matrix
        query_embeddings = embedding_service.extract_embedding_matrix(cropped_frames)
        logger.info(f"[Job {job_id}] Embedding matrix shape: {query_embeddings.shape}")

        # --- Step 12: Run unified IdentificationPipeline ---
        logger.info(f"[Job {job_id}] Running unified IdentificationPipeline")
        pipeline = get_identification_pipeline()

        pipeline_metadata = CaptureMetadata(
            species_slug=species_slug,
            area_code=job_doc.get("area_code"),
            latitude=job_doc.get("latitude"),
            longitude=job_doc.get("longitude"),
            gps_accuracy_m=job_doc.get("gps_accuracy_m"),
            gps_timestamp=job_doc.get("gps_timestamp"),
            gps_is_mocked=bool(job_doc.get("gps_is_mocked")),
            gps_source=job_doc.get("gps_source", "current"),
            area_selection_source=job_doc.get("area_selection_source", "user_selected"),
        )

        pipeline_result = pipeline.run(
            query_embeddings=query_embeddings,
            metadata=pipeline_metadata,
            quality_score=quality_score,
            valid_crop_count=len(cropped_frames),
            track_consistent=track_consistent,
            multiple_fish_detected=multiple_fish_detected,
        )

        # Extract decision from pipeline
        pipeline_decision = pipeline_result.decision  # auto_match, new_fish, needs_manual_review, repeat_capture
        matched_fish_id = pipeline_result.fish_id  # Only set for auto_match
        proposed_fish_id = pipeline_result.proposed_fish_id  # Set for needs_manual_review

        # Extract scoring details
        scoring = pipeline_result.scoring
        if scoring:
            match_confidence = scoring.top1_score
            top2_score = scoring.top2_score
            match_margin = scoring.margin
            candidates_evaluated = scoring.candidates_evaluated
        else:
            match_confidence = 0.0
            top2_score = 0.0
            match_margin = 0.0
            candidates_evaluated = 0

        decision_context = {
            "decision": pipeline_decision,
            "reasons": pipeline_result.reasons,
            "model_version": pipeline_result.model_version,
            "cross_area": pipeline_result.cross_area,
            "minimum_distance_m": pipeline_result.minimum_distance_m,
            "quality_score": quality_score,
            "track_consistent": track_consistent,
            "multiple_fish_detected": multiple_fish_detected,
        }

        is_new_fish = pipeline_decision == "new_fish"

        logger.info(
            f"[Job {job_id}] Pipeline decision: {pipeline_decision} "
            f"(score={match_confidence:.3f}, margin={match_margin:.3f}, "
            f"candidates={candidates_evaluated}, reasons={pipeline_result.reasons})"
        )

        # --- Step 12: Enter Critical DB Transaction (BEGIN IMMEDIATE) ---
        _emit_progress(job_id, "uploading_results", 95, "Saving artifacts and sightings")
        
        user_id = job_doc.get("user_id")
        area_code = job_doc.get("area_code", "XX")
        area_code_clean = normalize_area_code(area_code)
        sighting_id = str(uuid.uuid4())
        
        final_status = "completed"

        created_artifact_dir = None
        created_private_dir = None
        capture_artifacts = None
        linkage = None
        fish_id = None
        catch_number = 1

        try:
            cursor.execute("BEGIN IMMEDIATE")

            # Double Check Idempotency inside the write lock (Phase 2)
            cursor.execute("SELECT * FROM fish_sightings WHERE job_id = ? LIMIT 1", (job_id,))
            existing_sighting_p2 = cursor.fetchone()
            if existing_sighting_p2:
                logger.warning(f"[Job {job_id}] Sighting already created (Phase 2). Rolling back.")
                conn.rollback()
                
                # Fetch completed data
                sighting_data = dict(existing_sighting_p2)
                result = {
                    "status": "completed" if species_slug else "needs_review",
                    "job_id": job_id,
                    "fish_id": sighting_data.get("fish_id"),
                    "sighting_id": sighting_data.get("id"),
                    "species_slug": species_slug,
                    "species_english": species_info.get("english_name") if species_info else None,
                    "confidence": sighting_data.get("confidence", 0.0),
                    "is_new_fish": bool(sighting_data.get("is_new_fish")),
                    "xp_earned": sighting_data.get("xp_earned", 10),
                    "detection_confidence": sighting_data.get("detection_confidence", 0.0),
                    "match_confidence": sighting_data.get("match_confidence", 0.0),
                }
                return result

            # Resolve unique fish_id and catch number
            previous_sighting_id = None
            total_sightings_before = 0

            # --- RE-MATCH inside write lock to prevent concurrent duplicates ---
            # Another job may have stored a new embedding between our first match
            # (outside the lock) and now. Re-run the pipeline under the lock.
            pipeline_result_locked = pipeline.run(
                query_embeddings=query_embeddings,
                metadata=pipeline_metadata,
                quality_score=quality_score,
                valid_crop_count=len(cropped_frames),
                track_consistent=track_consistent,
                multiple_fish_detected=multiple_fish_detected,
            )

            # Use the locked result (may differ from pre-lock result)
            pipeline_decision = pipeline_result_locked.decision
            pipeline_result = pipeline_result_locked
            matched_fish_id = pipeline_result.fish_id
            proposed_fish_id = pipeline_result.proposed_fish_id
            scoring = pipeline_result.scoring
            if scoring:
                match_confidence = scoring.top1_score
                top2_score = scoring.top2_score
                match_margin = scoring.margin
                candidates_evaluated = scoring.candidates_evaluated
            is_new_fish = pipeline_decision == "new_fish"

            # --- DECISION LOGIC (via unified pipeline) ---
            # The pipeline has already made the decision: auto_match, new_fish,
            # needs_manual_review, or repeat_capture
            min_margin = getattr(settings, "reid_min_margin", 0.05)
            min_agreement = getattr(settings, "reid_min_agreement", 0.75)
            detection_confidence = best_detection_confidence if best_detection else 0.0

            if pipeline_decision == "auto_match":
                confidence_band = "high"
                linkage_decision = "auto_match"
                requires_human_review = False
            elif pipeline_decision == "new_fish":
                confidence_band = "new_fish"
                linkage_decision = "new_fish"
                requires_human_review = False
            elif pipeline_decision == "repeat_capture":
                confidence_band = "repeat_capture"
                linkage_decision = "repeat_capture"
                requires_human_review = True
            else:
                # needs_manual_review (gray zone, GPS uncertain, multiple fish, etc.)
                confidence_band = "gray_zone"
                linkage_decision = "needs_manual_review"
                requires_human_review = True

            if requires_human_review:
                # --- AMBIGUOUS PATH: Mark job as needs_manual_review ---
                # Do NOT create fish individual, sighting, or store embedding
                final_status = "needs_manual_review"
                xp_earned = 0

                linkage = {
                    "is_linked": False,
                    "strategy": "unified_pipeline_v1",
                    "threshold": settings.reid_similarity_threshold,
                    "matched_fish_id": None,
                    "proposed_fish_id": proposed_fish_id,
                    "proposed_score": round(match_confidence, 4),
                    "top2_fish_id": scoring.top2_fish_id if scoring else None,
                    "top2_score": round(top2_score, 4),
                    "margin": round(match_margin, 4),
                    "confidence_band": confidence_band,
                    "decision": linkage_decision,
                    "requires_human_review": True,
                    "reasons": pipeline_result.reasons,
                    "area_code": area_code_clean,
                    "latitude": job_doc.get("latitude"),
                    "longitude": job_doc.get("longitude"),
                    "nearby_area_radius_km": settings.nearby_area_radius_km,
                    "candidates_evaluated": candidates_evaluated,
                    "quality_score": quality_score,
                    "track_consistent": track_consistent,
                    "multiple_fish_detected": multiple_fish_detected,
                }

                # Update job status only — no sighting, no individual, no embedding
                cursor.execute(
                    """UPDATE identification_jobs 
                       SET status = ?, updated_at = ?, result_json = ?
                       WHERE id = ?""",
                    (
                        "needs_manual_review",
                        now_str,
                        json.dumps({"linkage": linkage, "species_slug": species_slug}, ensure_ascii=False),
                        job_id,
                    ),
                )
                conn.commit()

                logger.info(
                    f"[Job {job_id}] AMBIGUOUS result (score={match_confidence:.4f}, "
                    f"margin={match_margin:.4f}) — marked needs_manual_review. "
                    f"No individual or sighting created."
                )

                _emit_progress(job_id, "needs_manual_review", 100, "Requires human review")

                return {
                    "status": "needs_manual_review",
                    "job_id": job_id,
                    "fish_id": None,
                    "sighting_id": None,
                    "species_slug": species_slug,
                    "species_english": species_info.get("english_name") if species_info else None,
                    "confidence": round(match_confidence, 4),
                    "is_new_fish": False,
                    "xp_earned": 0,
                    "detection_confidence": round(detection_confidence, 4),
                    "match_confidence": round(match_confidence, 4),
                    "requires_human_review": True,
                    "linkage": linkage,
                }

            # --- DEFINITIVE PATH: auto_match or new_fish ---
            if is_new_fish:
                fish_id = _generate_fish_id(cursor, area_code_clean, species_slug)
                catch_number = 1
                logger.info(f"[Job {job_id}] Generated new fish_id: {fish_id}")
            else:
                fish_id = matched_fish_id
                cursor.execute(
                    """
                    SELECT latest_sighting_id, total_sightings
                    FROM fish_individuals
                    WHERE fish_id = ?
                    """,
                    (fish_id,),
                )
                existing_fish_row = cursor.fetchone()
                if existing_fish_row:
                    previous_sighting_id = existing_fish_row["latest_sighting_id"]
                    total_sightings_before = int(existing_fish_row["total_sightings"] or 0)
                    catch_number = total_sightings_before + 1
                else:
                    catch_number = 1
                    total_sightings_before = 0
                logger.info(f"[Job {job_id}] Using existing fish_id: {fish_id} (catch #{catch_number})")

            total_sightings_after = catch_number

            # Determine confidence values
            overall_confidence = (
                (detection_confidence + match_confidence) / 2.0
                if not is_new_fish
                else detection_confidence
            )
            if classification_confidence > 0:
                overall_confidence = max(overall_confidence, classification_confidence)

            xp_earned = _calculate_xp(species_info, is_new_fish)

            linkage = {
                "is_linked": not is_new_fish,
                "strategy": "unified_pipeline_v1",
                "threshold": settings.reid_similarity_threshold,
                "matched_fish_id": matched_fish_id,
                "final_fish_id": fish_id,
                "previous_sighting_id": previous_sighting_id,
                "match_confidence": round(match_confidence, 4),
                "top2_score": round(top2_score, 4),
                "margin": round(match_margin, 4),
                "confidence_band": confidence_band,
                "decision": linkage_decision,
                "requires_human_review": False,
                "reasons": pipeline_result.reasons,
                "total_sightings_before": total_sightings_before,
                "total_sightings_after": total_sightings_after,
                "same_species_required": True,
                "area_code": area_code_clean,
                "latitude": job_doc.get("latitude"),
                "longitude": job_doc.get("longitude"),
                "nearby_area_radius_km": settings.nearby_area_radius_km,
                "candidates_evaluated": candidates_evaluated,
                "quality_score": quality_score,
                "track_consistent": track_consistent,
                "multiple_fish_detected": multiple_fish_detected,
                "model_version": pipeline_result.model_version,
            }

            # Build document schema exactly as requested
            document = {
                "schema_version": "1.0",
                "job": {
                    "job_id": job_id,
                    "status": final_status,
                    "created_at": job_doc.get("created_at"),
                    "started_at": job_doc.get("started_at"),
                    "completed_at": now_str,
                },
                "user": {
                    "user_id": user_id,
                },
                "capture": {
                    "area_code": area_code_clean,
                    "area_name": job_doc.get("area_name"),
                    "latitude": job_doc.get("latitude"),
                    "longitude": job_doc.get("longitude"),
                    "weather": job_doc.get("weather"),
                    "bait": job_doc.get("bite"),
                    "size_cm": job_doc.get("size_cm"),
                    "fish_state": job_doc.get("fish_state"),
                    "custom_name": job_doc.get("custom_name"),
                    "notes": job_doc.get("notes"),
                },
                "species": {
                    "slug": species_slug,
                    "english_name": species_info.get("english_name") if species_info else None,
                    "czech_name": species_info.get("czech_name") if species_info else None,
                    "latin_name": species_info.get("latin_name") if species_info else None,
                    "rarity": species_info.get("rarity") if species_info else "common",
                },
                "fish": {
                    "fish_id": fish_id,
                    "is_new_fish": is_new_fish,
                    "catch_number": catch_number,
                    "previous_sighting_id": previous_sighting_id,
                    "total_sightings_before": total_sightings_before,
                    "total_sightings_after": total_sightings_after,
                },
                "linkage": linkage,
                "model": {
                    "detector_type": settings.detector_type,
                    "detector_model_path": settings.detector_model_path,
                    "classifier_model_path": settings.classifier_model_path,
                    "detection_confidence": round(detection_confidence, 4),
                    "classification_confidence": round(classification_confidence, 4),
                    "match_confidence": round(match_confidence, 4),
                    "overall_confidence": round(overall_confidence, 4),
                    "top_predictions": (
                        classification_result.get("predictions", [])
                        if classification_result else []
                    ),
                },
                "media": {
                    "media_type": media_type,
                    "preview": None,
                    "video": None,
                    "images": [],
                    "frames": [],
                },
                "gamification": {
                    "xp_earned": xp_earned,
                },
            }

            model_outputs = {
                "classification_result": classification_result,
                "detection_confidence": round(detection_confidence, 4),
                "classification_confidence": round(classification_confidence, 4),
                "match_confidence": round(match_confidence, 4),
                "overall_confidence": round(overall_confidence, 4),
                "detector_type": settings.detector_type,
                "detector_model_path": settings.detector_model_path,
                "classifier_model_path": settings.classifier_model_path,
            }

            # Save final persistent folders (catch_{catch_number}_{job_id})
            capture_artifacts = save_fish_capture_artifacts(
                job_id=job_id,
                sighting_id=sighting_id,
                area_code=area_code_clean,
                species_slug=species_slug or "unknown_species",
                fish_id=fish_id,
                catch_number=catch_number,
                selected_frames=best_frames,
                cropped_frames=cropped_frames,
                cropped_frames_bbox=cropped_frames_bbox,
                raw_video_path=temp_video_path,
                document=document,
                model_outputs=model_outputs,
                media_type=media_type,
                is_new_fish=is_new_fish,
                linkage=linkage,
                # Annotation + dataset params
                best_detection_frame=best_detection_frame,
                best_detection=best_detection,
                species_english=species_info.get("english_name") if species_info else None,
                detection_confidence=detection_confidence,
                classification_confidence=classification_confidence,
                match_confidence=match_confidence,
                model_type=settings.detector_type or "yolov8_obb",
                all_dataset_detections=dataset_frame_detections,
            )

            created_artifact_dir = capture_artifacts.get("artifact_abs_dir")
            created_private_dir = capture_artifacts.get("private_abs_dir")
            frame_filename = capture_artifacts.get("preview_filename")

            # Insert fish_sightings
            cursor.execute(
                """INSERT INTO fish_sightings (
                    id, user_id, fish_id, job_id, species_slug, species_english, species_czech, species_latin, 
                    confidence, is_new_fish, xp_earned, area_code, frame_filename, raw_video_filename, 
                    captured_at, created_at, location_lat, location_lng,
                    area_name, weather, bite, size_cm, fish_state, custom_name, notes,
                    artifact_dir, document_filename, preview_filename, annotated_preview_filename,
                    detection_confidence, classification_confidence, match_confidence, catch_number,
                    media_type, video_filename, rarity,
                    previous_sighting_id, total_sightings_before, total_sightings_after, linkage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sighting_id, user_id, fish_id, job_id, species_slug,
                    species_info.get("english_name") if species_info else None,
                    species_info.get("czech_name") if species_info else None,
                    species_info.get("latin_name") if species_info else None,
                    round(overall_confidence, 4), 1 if is_new_fish else 0, xp_earned, area_code_clean,
                    frame_filename, raw_video_filename,
                    job_doc.get("created_at", now_str), now_str,
                    job_doc.get("latitude"), job_doc.get("longitude"),
                    job_doc.get("area_name"),
                    job_doc.get("weather"),
                    job_doc.get("bite"),
                    job_doc.get("size_cm"),
                    job_doc.get("fish_state"),
                    job_doc.get("custom_name"),
                    job_doc.get("notes"),
                    capture_artifacts.get("artifact_dir"),
                    capture_artifacts.get("document_filename"),
                    capture_artifacts.get("preview_filename"),
                    capture_artifacts.get("annotated_preview_filename"),
                    round(detection_confidence, 4),
                    round(classification_confidence, 4),
                    round(match_confidence, 4),
                    catch_number,
                    media_type,
                    capture_artifacts.get("video_filename"),
                    species_info.get("rarity") if species_info else "common",
                    previous_sighting_id,
                    total_sightings_before,
                    total_sightings_after,
                    json.dumps(linkage, ensure_ascii=False)
                )
            )

            # Insert/Update fish_individuals
            if is_new_fish:
                logger.info(f"[Job {job_id}] Creating new fish_individuals record")
                cursor.execute(
                    """INSERT INTO fish_individuals (
                        id, fish_id, species_slug, species_english, species_latin, 
                        first_seen_by, first_seen_at, last_seen_at, total_sightings, area_code, best_frame_filename,
                        area_name, latest_sighting_id, latest_document_filename,
                        first_sighting_id, reference_frame_filename, max_size_cm,
                        last_seen_by, first_seen_lat, first_seen_lng, last_seen_lat, last_seen_lng, linkage_updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), fish_id, species_slug,
                        species_info.get("english_name") if species_info else None,
                        species_info.get("latin_name") if species_info else None,
                        user_id, now_str, now_str, area_code_clean, frame_filename,
                        job_doc.get("area_name"), sighting_id, capture_artifacts.get("document_filename"),
                        sighting_id, frame_filename, job_doc.get("size_cm"),
                        user_id, job_doc.get("latitude"), job_doc.get("longitude"),
                        job_doc.get("latitude"), job_doc.get("longitude"), now_str
                    )
                )
            else:
                logger.info(f"[Job {job_id}] Updating existing fish_individuals record")
                cursor.execute(
                    """UPDATE fish_individuals 
                       SET last_seen_at = ?, 
                           total_sightings = total_sightings + 1,
                           latest_sighting_id = ?, 
                           latest_document_filename = ?,
                           last_seen_by = ?,
                           last_seen_lat = ?,
                           last_seen_lng = ?,
                           max_size_cm = CASE
                               WHEN max_size_cm IS NULL THEN ?
                               WHEN ? IS NOT NULL AND ? > max_size_cm THEN ?
                               ELSE max_size_cm
                           END,
                           linkage_updated_at = ?
                       WHERE fish_id = ?""",
                    (
                        now_str, sighting_id, capture_artifacts.get("document_filename"),
                        user_id, job_doc.get("latitude"), job_doc.get("longitude"),
                        job_doc.get("size_cm"), job_doc.get("size_cm"), job_doc.get("size_cm"), job_doc.get("size_cm"),
                        now_str, fish_id
                    )
                )

            # Update User statistics
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

            # Store embedding (averaged prototype for the embedding index)
            embedding_vector = np.mean(query_embeddings, axis=0)
            embedding_vector = embedding_vector / (np.linalg.norm(embedding_vector) + 1e-12)
            matching.store_embedding(
                fish_id=fish_id,
                embedding=embedding_vector,
                species_slug=species_slug,
                area_code=area_code_clean,
                sighting_id=sighting_id,
                latitude=job_doc.get("latitude"),
                longitude=job_doc.get("longitude"),
            )

            # Update identification_jobs final status
            cursor.execute(
                """UPDATE identification_jobs 
                   SET status = ?, completed_at = ?, result_sighting_id = ?, result_fish_id = ?, 
                       confidence = ?, species_slug = ?, is_new_fish = ?, xp_earned = ?, error_message = NULL,
                       artifact_dir = ?, document_filename = ?, preview_filename = ?, annotated_preview_filename = ?,
                       video_filename = ?, rarity = ?, detection_confidence = ?, classification_confidence = ?,
                       match_confidence = ?, catch_number = ?, linked_fish_id = ?, previous_sighting_id = ?,
                       total_sightings_before = ?, total_sightings_after = ?, linkage_json = ?
                   WHERE id = ?""",
                (
                    final_status, now_str, sighting_id, fish_id,
                    round(overall_confidence, 4), species_slug, 1 if is_new_fish else 0, xp_earned,
                    capture_artifacts.get("artifact_dir"),
                    capture_artifacts.get("document_filename"),
                    capture_artifacts.get("preview_filename"),
                    capture_artifacts.get("annotated_preview_filename"),
                    capture_artifacts.get("video_filename"),
                    species_info.get("rarity") if species_info else "common",
                    round(detection_confidence, 4),
                    round(classification_confidence, 4),
                    round(match_confidence, 4),
                    catch_number,
                    fish_id if not is_new_fish else None,
                    previous_sighting_id,
                    total_sightings_before,
                    total_sightings_after,
                    json.dumps(linkage, ensure_ascii=False),
                    job_id
                )
            )

            conn.commit()

            # --- Step 13: POST-COMMIT: Update fish_index.json summary file safely ---
            try:
                index_path = Path(settings.private_data_dir) / capture_artifacts.get("fish_index_filename")
                entry_data = {
                    "job_id": job_id,
                    "sighting_id": sighting_id,
                    "fish_id": fish_id,
                    "area_code": area_code_clean,
                    "species_slug": species_slug or "unknown_species",
                    "catch_number": catch_number,
                    "is_new_fish": is_new_fish,
                    "created_at": now_str,
                    "preview_url": capture_artifacts.get("media", {}).get("preview"),
                    "raw_url": capture_artifacts.get("media", {}).get("raw"),
                    "document_filename": capture_artifacts.get("document_filename"),
                    "manifest_filename": capture_artifacts.get("manifest_filename"),
                    "artifact_dir": capture_artifacts.get("artifact_dir"),
                    "linkage": linkage,
                }
                update_fish_index_file(index_path, entry_data)
            except Exception as index_err:
                logger.error(f"[Job {job_id}] Failed to write index file post-commit: {index_err}")

        except Exception as tx_err:
            try:
                conn.rollback()
            except Exception:
                pass
            # Cleanup filesystem directories to prevent orphans
            if created_artifact_dir:
                shutil.rmtree(created_artifact_dir, ignore_errors=True)
            if created_private_dir:
                shutil.rmtree(created_private_dir, ignore_errors=True)
            raise tx_err

        # --- Step 14: Return results ---
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
