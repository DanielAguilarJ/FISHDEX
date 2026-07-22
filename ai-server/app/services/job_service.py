import logging
import uuid
import os
import io
import asyncio
import cv2
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional
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
from dataclasses import dataclass, field
from app.utils.video import (
    cleanup_temp_file,
    extract_frames_from_video,
    iter_frames_from_video,
    DecodedVideoFrame,
    select_best_n_frames,
)
from app.utils.area_utils import normalize_area_code
from app.utils.crop_utils import crop_fish_best, crop_obb_rotated, crop_bbox_aligned_strict, crop_bbox_preserve_frame_aspect

logger = logging.getLogger(__name__)


@dataclass
class FrameCandidateMetadata:
    """Lightweight candidate metadata — does NOT hold frame/crop arrays."""
    frame_index: int
    timestamp_seconds: float
    score: float
    detection: Any
    confidence: float
    detection_index: int = 0   # index within frame's valid detections
    track_id: Optional[int] = None


@dataclass
class FrameCandidate:
    frame_index: int
    timestamp_seconds: float
    score: float
    frame: np.ndarray
    detection: Any
    confidence: float
    crop: np.ndarray
    track_id: Optional[int] = None

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


def _crop_primary_reid_roi(frame: np.ndarray, detection) -> Optional[np.ndarray]:
    """
    Returns the complete fish ROI used as input to ReID and storage.

    When fingerprint mode is active, REQUIRES a valid OBB-rectified ROI
    (axis-aligned bbox would produce incorrect anatomical coordinates).
    Legacy full-fish mode retains the bbox fallback.
    """
    if settings.reid_fingerprint_crop_enabled:
        # Strict: only OBB-rectified crop for fingerprint mode
        result = crop_obb_rotated(frame, detection, pad_frac=settings.crop_padding_frac)
        if result is None or result.size == 0:
            return None  # Do NOT fall back to bbox
        return result

    # Legacy mode: try OBB first, then bbox
    return crop_fish_best(frame, detection, pad_frac=settings.crop_padding_frac)


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


def _sharpness_score(image: np.ndarray) -> float:
    """Laplacian variance as sharpness metric. Operates on the provided image
    (should be the crop, not the full frame, for accuracy)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _candidate_score(frame: np.ndarray, detection, crop: Optional[np.ndarray] = None) -> float:
    """Combined quality score: 70% confidence + 20% sharpness + 10% tightness.
    If crop is provided, sharpness is measured on the crop (more accurate).
    Otherwise falls back to full frame."""
    conf = _get_detection_confidence(detection)
    sharpness_source = crop if (crop is not None and crop.size > 0) else frame
    sharp = min(_sharpness_score(sharpness_source) / 500.0, 1.0)
    area_ratio = _detection_area_ratio(detection, frame.shape)
    # Penalize large boxes
    area_quality = 1.0 - min(max(area_ratio - 0.35, 0.0) / 0.30, 1.0)
    return (0.70 * conf) + (0.20 * sharp) + (0.10 * area_quality)


def _select_with_temporal_diversity(
    candidates: list["FrameCandidate"],
    max_count: int = 5,
    min_gap_seconds: float = 0.30,
) -> list["FrameCandidate"]:
    """
    Select top candidates with temporal diversity (temporal NMS).

    Sorts by quality (score descending, frame_index as tiebreaker), then
    greedily picks candidates that are at least min_gap_seconds apart from
    all previously selected.

    Does NOT backfill with temporally-close frames. If only 2 diverse frames
    exist, returns 2 — never pads with near-duplicates.
    """
    if not candidates:
        return []
    if max_count < 1:
        max_count = 1
    if min_gap_seconds < 0:
        min_gap_seconds = 0.0

    # Sort by quality descending, frame_index as deterministic tiebreaker
    sorted_cands = sorted(candidates, key=lambda c: (-c.score, c.frame_index))

    selected: list["FrameCandidate"] = []
    for cand in sorted_cands:
        if len(selected) >= max_count:
            break
        # Check temporal distance from all already selected
        too_close = False
        for sel in selected:
            gap = abs(cand.timestamp_seconds - sel.timestamp_seconds)
            if gap < min_gap_seconds:
                too_close = True
                break
        if not too_close:
            selected.append(cand)

    return selected

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


def _build_similarity_reference(
    pipeline_result,
    scoring,
    cursor,
    pipeline_decision: str,
) -> Optional[dict]:
    """
    Build the similarity_reference object from pipeline result.

    This identifies the exact historical capture whose embedding produced
    the highest similarity with the current query.

    Returns None if no scoring or no candidates were evaluated.
    """
    if not scoring or not scoring.top1_fish_id:
        return None

    ref = pipeline_result.reference_sighting_id
    ref_embedding_id = pipeline_result.reference_embedding_id
    ref_score = pipeline_result.reference_score

    # Determine status based on decision
    if pipeline_decision == "auto_match":
        status = "accepted"
    elif pipeline_decision == "new_fish":
        status = "rejected"
    else:
        status = "rejected"

    # Load reference sighting details if available
    reference_row = None
    if ref:
        cursor.execute(
            """SELECT id, job_id, fish_id, catch_number, area_code, area_name,
                      captured_at, created_at, preview_filename, artifact_dir, size_cm
               FROM fish_sightings WHERE id = ? LIMIT 1""",
            (ref,),
        )
        row = cursor.fetchone()
        if row:
            reference_row = dict(row)
            # Validate consistency
            if reference_row.get("fish_id") != scoring.top1_fish_id:
                logger.warning(
                    "Reference sighting fish_id mismatch: %s != %s",
                    reference_row.get("fish_id"),
                    scoring.top1_fish_id,
                )
                # Still include but note the inconsistency
                pass

    similarity_reference = {
        "status": status,
        "candidate_fish_id": scoring.top1_fish_id,
        "reference_sighting_id": ref,
        "reference_embedding_id": ref_embedding_id,
        "reference_job_id": reference_row["job_id"] if reference_row else None,
        "reference_catch_number": reference_row["catch_number"] if reference_row else None,
        "identity_score": round(scoring.top1_score, 4),
        "reference_score": round(ref_score, 4) if ref_score else None,
        "threshold": settings.reid_similarity_threshold,
        "margin": round(scoring.margin, 4),
        "reference_area_code": pipeline_result.reference_area_code,
        "reference_area_name": reference_row["area_name"] if reference_row else None,
        "reference_captured_at": reference_row["captured_at"] if reference_row else None,
        "reference_preview_url": (
            f"/storage/{reference_row['preview_filename']}"
            if reference_row and reference_row.get("preview_filename")
            else None
        ),
        "distance_m": (
            round(pipeline_result.reference_distance_m, 1)
            if pipeline_result.reference_distance_m is not None
            else None
        ),
        "cross_area": pipeline_result.cross_area,
        "model_version": pipeline_result.model_version,
        "selection_method": "highest_median_query_similarity_within_winning_identity",
    }

    return similarity_reference


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
                logger.info(
                    f"[Job {job_id}] Already in 'processing' status. "
                    "Exiting gracefully to avoid race condition."
                )
                return {
                    "status": "already_processing",
                    "job_id": job_id,
                    "message": "Job is being processed by another instance",
                }
            elif current_status == "failed" and not force:
                raise ValueError(f"Job {job_id} previously failed. Use force=True to retry.")

        # --- Step 3: Atomically transition status to processing ---
        # Uses WHERE status='uploaded' (or 'pending_crop') to prevent race conditions.
        # If another instance already claimed this job, rowcount will be 0.
        logger.info(f"[Job {job_id}] Attempting atomic status transition to 'processing'")
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE identification_jobs SET status = 'processing', started_at = ?, error_message = NULL "
            "WHERE id = ? AND status IN ('uploaded', 'pending_crop')",
            (now_str, job_id)
        )
        conn.commit()
        
        if cursor.rowcount == 0:
            # Another process already claimed this job — exit gracefully
            logger.info(
                f"[Job {job_id}] Could not acquire processing lock "
                f"(current_status={current_status}). Another instance is handling it."
            )
            return {
                "status": "already_processing",
                "job_id": job_id,
                "message": "Job is being processed by another instance",
            }

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

        # --- Step 5 & 6 & 7: Sequential frame decoding + single-pass detection + global candidate collection ---
        _emit_progress(job_id, "detecting_fish", 50, f"Scanning {media_type} frames with YOLOv8 OBB detector")
        logger.info(f"[Job {job_id}] Decoding all frames and scoring candidates")

        base_threshold = settings.detector_confidence_threshold or 0.30

        decoded_frame_count = 0
        detector_call_count = 0
        retry_detector_calls = 0
        frames_with_valid_detection = 0
        frames_rejected_multiple_detections = 0
        # Lightweight metadata — NO frame/crop arrays stored
        candidate_metadata: list[FrameCandidateMetadata] = []
        frame_detections_for_tracking: list[list[dict]] = []
        video_duration_seconds = 0.0
        top_candidates: list[FrameCandidate] = []

        if media_type == "image":
            img = cv2.imread(temp_video_path)
            if img is None:
                raise ValueError(f"Could not read image file: {temp_video_path}")
            frames_iter = [DecodedVideoFrame(frame_index=0, timestamp_seconds=0.0, frame=img)]
        else:
            frames_iter = iter_frames_from_video(temp_video_path, max_side=settings.frame_max_side or 960)

        if recovered_candidate is not None:
            recovered_frame = recovered_candidate.get("frame")
            recovered_detection = recovered_candidate.get("detection")
            recovered_confidence = float(recovered_candidate.get("confidence", 0.0) or 0.0)
            if not isinstance(recovered_frame, np.ndarray) or recovered_frame.size == 0 or recovered_detection is None:
                raise ValueError("Recovered candidate invalid")
            rec_crop = _crop_primary_reid_roi(recovered_frame, recovered_detection)
            if rec_crop is not None and rec_crop.size > 0:
                recovered_score = _candidate_score(recovered_frame, recovered_detection, crop=rec_crop)
                top_candidates.append(
                    FrameCandidate(
                        frame_index=0,
                        timestamp_seconds=0.0,
                        score=recovered_score,
                        frame=recovered_frame,
                        detection=recovered_detection,
                        confidence=recovered_confidence,
                        crop=rec_crop,
                    )
                )
                decoded_frame_count = 1
                detector_call_count = 1
                frames_with_valid_detection = 1
        else:
            # --- First pass: collect lightweight metadata + tracking detections ---
            for decoded in frames_iter:
                decoded_frame_count += 1
                frame = decoded.frame
                f_idx = decoded.frame_index
                t_sec = decoded.timestamp_seconds

                detector_call_count += 1
                detections = detector.detect(frame, conf_threshold=base_threshold)

                valid_frame_dets: list[dict] = []
                best_meta_in_frame: Optional[FrameCandidateMetadata] = None
                best_score_in_frame = -1.0
                best_det_index = 0

                for det_idx, det in enumerate(detections):
                    if _is_valid_tight_detection(det, frame.shape, min_conf=base_threshold):
                        bbox = _get_detection_bbox(det)
                        if bbox and len(bbox) >= 4:
                            x1, y1, x2, y2 = bbox
                            xywh = [
                                float(x1),
                                float(y1),
                                float(max(0.0, x2 - x1)),
                                float(max(0.0, y2 - y1)),
                            ]
                            conf_val = _get_detection_confidence(det)
                            valid_frame_dets.append({"bbox": xywh, "confidence": conf_val})

                        # Score using lightweight sharpness estimate from frame region
                        # (full crop will be generated only for final candidates)
                        score = _candidate_score(frame, det)
                        if score > best_score_in_frame:
                            best_score_in_frame = score
                            best_det_index = len(valid_frame_dets) - 1 if valid_frame_dets else 0
                            best_meta_in_frame = FrameCandidateMetadata(
                                frame_index=f_idx,
                                timestamp_seconds=t_sec,
                                score=score,
                                detection=det,
                                confidence=_get_detection_confidence(det),
                                detection_index=best_det_index,
                            )

                if valid_frame_dets:
                    frames_with_valid_detection += 1
                frame_detections_for_tracking.append(valid_frame_dets)

                # Reject frames with multiple valid detections when single-detection is required
                if settings.roi_require_single_detection and len(valid_frame_dets) > 1:
                    frames_rejected_multiple_detections += 1
                    best_meta_in_frame = None  # Do not add to candidate pool

                if best_meta_in_frame is not None:
                    candidate_metadata.append(best_meta_in_frame)

            if media_type == "video" and decoded_frame_count > 0:
                try:
                    cap_info = cv2.VideoCapture(temp_video_path)
                    fps_val = cap_info.get(cv2.CAP_PROP_FPS) or 0.0
                    cap_info.release()
                    video_duration_seconds = (decoded_frame_count / fps_val) if fps_val > 0 else 0.0
                except Exception:
                    video_duration_seconds = 0.0

            # Retries if no valid candidates were found in primary pass
            if not candidate_metadata and media_type == "video":
                retry_thresholds = [0.25, 0.20]
                for retry_idx, retry_thresh in enumerate(retry_thresholds, start=1):
                    logger.info(f"[Job {job_id}] Detection retry {retry_idx}: threshold={retry_thresh}")
                    # Reset tracking for retry — use retry's own detections
                    retry_frame_detections: list[list[dict]] = []
                    retry_candidates: list[FrameCandidateMetadata] = []
                    r_frames_iter = iter_frames_from_video(temp_video_path, max_side=settings.frame_max_side or 960)
                    for decoded in r_frames_iter:
                        frame = decoded.frame
                        retry_detector_calls += 1
                        detections = detector.detect(frame, conf_threshold=retry_thresh)
                        valid_dets_in_frame: list[dict] = []
                        for det in detections:
                            if _is_valid_tight_detection(det, frame.shape, min_conf=retry_thresh):
                                bbox = _get_detection_bbox(det)
                                if bbox and len(bbox) >= 4:
                                    x1, y1, x2, y2 = bbox
                                    xywh = [float(x1), float(y1), float(max(0.0, x2-x1)), float(max(0.0, y2-y1))]
                                    valid_dets_in_frame.append({"bbox": xywh, "confidence": _get_detection_confidence(det)})

                        retry_frame_detections.append(valid_dets_in_frame)

                        # Same single-detection policy in retry
                        if settings.roi_require_single_detection and len(valid_dets_in_frame) > 1:
                            frames_rejected_multiple_detections += 1
                            continue
                        for det in detections:
                            if _is_valid_tight_detection(det, frame.shape, min_conf=retry_thresh):
                                score = _candidate_score(frame, det)
                                retry_candidates.append(
                                    FrameCandidateMetadata(
                                        frame_index=decoded.frame_index,
                                        timestamp_seconds=decoded.timestamp_seconds,
                                        score=score,
                                        detection=det,
                                        confidence=_get_detection_confidence(det),
                                        detection_index=0,
                                    )
                                )
                    if retry_candidates:
                        # Use retry's candidates AND tracking detections coherently
                        candidate_metadata = retry_candidates
                        frame_detections_for_tracking = retry_frame_detections
                        break

            # --- Run tracking over ALL frame detections (chronological) ---
            tracking_result = validate_single_fish(frame_detections_for_tracking)
            track_consistent = tracking_result.is_single_fish
            multiple_fish_detected = tracking_result.multiple_fish_detected

            # --- Assign track IDs to candidates ---
            for meta in candidate_metadata:
                frame_tracks = tracking_result.track_ids_per_frame
                if meta.frame_index < len(frame_tracks):
                    frame_track_ids = frame_tracks[meta.frame_index]
                    if meta.detection_index < len(frame_track_ids):
                        meta.track_id = frame_track_ids[meta.detection_index]
                    elif frame_track_ids:
                        # Best detection might map to first valid detection
                        meta.track_id = frame_track_ids[0]

            # --- Filter by dominant track ---
            dominant_track_id = tracking_result.dominant_track_id
            dominant_candidates = [
                m for m in candidate_metadata
                if m.track_id == dominant_track_id or m.track_id is None
            ]
            # If filtering by track removes all candidates, keep all (single-fish case)
            if dominant_candidates:
                candidate_metadata = dominant_candidates

            # --- Apply temporal diversity selection on metadata ---
            max_selected = settings.reid_max_selected_candidates
            min_gap = settings.reid_min_selected_frame_gap_seconds
            temporal_diversity_applied = len(candidate_metadata) > 0

            # Create temporary FrameCandidate-like objects for selection
            # (reuse the same function signature by wrapping metadata)
            class _MetaWrapper:
                def __init__(self, m):
                    self.frame_index = m.frame_index
                    self.timestamp_seconds = m.timestamp_seconds
                    self.score = m.score

            meta_wrappers = [_MetaWrapper(m) for m in candidate_metadata]
            # Sort by quality descending with temporal gap
            selected_meta_indices: list[int] = []
            meta_wrappers_sorted = sorted(
                range(len(meta_wrappers)),
                key=lambda i: (-meta_wrappers[i].score, meta_wrappers[i].frame_index),
            )
            for idx in meta_wrappers_sorted:
                if len(selected_meta_indices) >= max_selected:
                    break
                too_close = False
                for sel_idx in selected_meta_indices:
                    gap = abs(meta_wrappers[idx].timestamp_seconds - meta_wrappers[sel_idx].timestamp_seconds)
                    if gap < min_gap:
                        too_close = True
                        break
                if not too_close:
                    selected_meta_indices.append(idx)

            selected_metadata = [candidate_metadata[i] for i in selected_meta_indices]

            # --- Second pass: reconstruct only selected frames/crops ---
            # Re-decode video to get only the frames we need (no re-detection)
            if selected_metadata and media_type != "image":
                needed_frame_indices = set(m.frame_index for m in selected_metadata)
                meta_by_frame = {m.frame_index: m for m in selected_metadata}

                r_frames_iter = iter_frames_from_video(temp_video_path, max_side=settings.frame_max_side or 960)
                for decoded in r_frames_iter:
                    if decoded.frame_index in needed_frame_indices:
                        meta = meta_by_frame[decoded.frame_index]
                        crop = _crop_primary_reid_roi(decoded.frame, meta.detection)
                        if crop is not None and crop.size > 0:
                            # Rescore with actual crop sharpness
                            score = _candidate_score(decoded.frame, meta.detection, crop=crop)
                            top_candidates.append(
                                FrameCandidate(
                                    frame_index=meta.frame_index,
                                    timestamp_seconds=meta.timestamp_seconds,
                                    score=score,
                                    frame=decoded.frame,
                                    detection=meta.detection,
                                    confidence=meta.confidence,
                                    crop=crop,
                                    track_id=meta.track_id,
                                )
                            )
                        needed_frame_indices.discard(decoded.frame_index)
                    if not needed_frame_indices:
                        break
            elif selected_metadata and media_type == "image":
                # For images, frame is already available
                for meta in selected_metadata:
                    frame = cv2.imread(temp_video_path)
                    if frame is not None:
                        crop = _crop_primary_reid_roi(frame, meta.detection)
                        if crop is not None and crop.size > 0:
                            score = _candidate_score(frame, meta.detection, crop=crop)
                            top_candidates.append(
                                FrameCandidate(
                                    frame_index=meta.frame_index,
                                    timestamp_seconds=meta.timestamp_seconds,
                                    score=score,
                                    frame=frame,
                                    detection=meta.detection,
                                    confidence=meta.confidence,
                                    crop=crop,
                                    track_id=meta.track_id,
                                )
                            )

            # Sort final candidates by score
            top_candidates.sort(key=lambda c: (-c.score, c.frame_index))

        # If STILL no valid candidates → mark pending_crop
        if not top_candidates:
            logger.warning(f"[Job {job_id}] No valid tight detection found after scanning. Marking pending_crop.")
            _emit_progress(job_id, "pending_crop", 100, "No tight fish detection found; queued for retry")
            job_artifacts = save_job_artifacts(
                job_id=job_id,
                selected_frames=[],
                cropped_frames=[],
                raw_video_path=temp_video_path,
            )
            cursor.execute(
                """UPDATE identification_jobs
                   SET status = 'pending_crop', error_message = ?,
                       preview_filename = ?, artifact_dir = ?, completed_at = ?
                   WHERE id = ?""",
                (
                    "No valid tight fish detection found. Queued for background retry.",
                    None,
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
                "preview_filename": None,
            }

        selected_candidates = top_candidates
        best_frames = [c.frame for c in selected_candidates]
        cropped_frames = [c.crop for c in selected_candidates]

        # best_candidate is highest quality for preview/detection info
        best_candidate = selected_candidates[0]
        best_score = best_candidate.score
        best_detection_frame = best_candidate.frame
        best_detection = best_candidate.detection
        best_detection_confidence = best_candidate.confidence

        dataset_frame_detections = [
            (c.frame, c.detection, c.confidence)
            for c in selected_candidates
        ]

        processing_stats = {
            "decoded_frames": decoded_frame_count,
            "detector_calls": detector_call_count,
            "retry_detector_calls": retry_detector_calls,
            "frames_with_valid_detection": frames_with_valid_detection,
            "frames_rejected_multiple_detections": frames_rejected_multiple_detections,
            "selected_frame_count": len(selected_candidates),
            "selected_frame_indices": [c.frame_index for c in selected_candidates],
            "selected_frame_timestamps": [round(c.timestamp_seconds, 4) for c in selected_candidates],
            "selected_frame_scores": [round(c.score, 6) for c in selected_candidates],
            "selected_track_ids": [c.track_id for c in selected_candidates],
            "dominant_track_id": tracking_result.dominant_track_id if 'tracking_result' in dir() else None,
            "minimum_selected_frame_gap_seconds": min_gap if 'min_gap' in dir() else 0.0,
            "temporal_diversity_applied": temporal_diversity_applied if 'temporal_diversity_applied' in dir() else False,
            "tracking_total_detections": tracking_result.total_detections if 'tracking_result' in dir() else 0,
            "tracking_dominant_track_length": tracking_result.dominant_track_length if 'tracking_result' in dir() else 0,
            "tracking_secondary_tracks": tracking_result.secondary_tracks if 'tracking_result' in dir() else 0,
            "multiple_fish_detected": tracking_result.multiple_fish_detected if 'tracking_result' in dir() else False,
            "selection_method": "temporal_diversity_track_filtered",
        }
        logger.info(f"[Job {job_id}] Processing stats: {processing_stats}")

        cropped_frames_bbox = []
        for c in selected_candidates:
            bbox_crop = crop_bbox_aligned_strict(
                c.frame,
                c.detection,
                pad_frac=settings.crop_padding_frac,
            )
            if bbox_crop is not None and bbox_crop.size > 0:
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

        # --- Step 10: Quality assessment (tracking already done in selection phase) ---
        _emit_progress(job_id, "analyzing_quality", 75, "Assessing capture quality and tracking")

        detection_dicts_for_quality: list[dict] = []
        selected_timestamps: list[float] = []

        for c in selected_candidates:
            selected_timestamps.append(c.timestamp_seconds)
            bbox = _get_detection_bbox(c.detection)
            if bbox and len(bbox) >= 4:
                x1, y1, x2, y2 = bbox
                xywh = [
                    float(x1),
                    float(y1),
                    float(max(0.0, x2 - x1)),
                    float(max(0.0, y2 - y1)),
                ]
                det_dict = {
                    "bbox": xywh,
                    "confidence": float(c.confidence),
                    "frame_height": c.frame.shape[0],
                    "frame_width": c.frame.shape[1],
                }
                detection_dicts_for_quality.append(det_dict)

        # Use tracking result from selection phase (already computed)
        if 'tracking_result' not in dir():
            tracking_result = validate_single_fish(frame_detections_for_tracking)
        track_consistent = tracking_result.is_single_fish
        multiple_fish_detected = tracking_result.multiple_fish_detected

        # Assess capture quality with real duration and timestamps
        quality_result = evaluate_capture(
            cropped_frames=cropped_frames,
            detections=detection_dicts_for_quality,
            frame_timestamps=selected_timestamps,
            video_duration_seconds=video_duration_seconds if media_type == "video" else 0.0,
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
            "processing_stats": processing_stats,
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
            # The pipeline always gives a definitive decision: auto_match, new_fish,
            # or repeat_capture. It NEVER returns needs_manual_review.
            min_margin = getattr(settings, "reid_min_margin", 0.05)
            min_agreement = getattr(settings, "reid_min_agreement", 0.75)
            detection_confidence = best_detection_confidence if best_detection else 0.0

            if pipeline_decision == "auto_match":
                # Use the identity_decision confidence_band (could be "high" or "forced")
                confidence_band = getattr(pipeline_result.identity_decision, 'confidence_band', 'high') if pipeline_result.identity_decision else "high"
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
                # Unexpected decision — treat as new_fish to never block
                logger.warning(f"[Job {job_id}] Unexpected pipeline_decision='{pipeline_decision}' — treating as new_fish")
                confidence_band = "new_fish"
                linkage_decision = "new_fish"
                requires_human_review = False

            if requires_human_review:
                # --- REPEAT CAPTURE PATH: quality too low ---
                # Do NOT create fish individual, sighting, or store embedding
                final_status = "repeat_capture"
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
                    "requires_human_review": False,
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

                # Build similarity reference for the repeat capture case
                similarity_reference = _build_similarity_reference(
                    pipeline_result, scoring, cursor, pipeline_decision,
                )
                linkage["similarity_reference"] = similarity_reference

                # Save complete ROI crops (the fish, not the fingerprint)
                try:
                    review_artifacts = save_job_artifacts(
                        job_id=job_id,
                        selected_frames=[],
                        cropped_frames=cropped_frames,
                        raw_video_path=temp_video_path,
                    )
                    review_artifact_dir = review_artifacts.get("job_artifact_dir")
                    review_preview = review_artifacts.get("preview_filename")
                except Exception as art_err:
                    logger.warning(f"[Job {job_id}] Failed to save artifacts: {art_err}")
                    review_artifact_dir = None
                    review_preview = None

                # Update job status only — no sighting, no individual, no embedding
                cursor.execute(
                    """UPDATE identification_jobs 
                       SET status = ?, updated_at = ?, result_json = ?,
                           match_reference_fish_id = ?,
                           match_reference_sighting_id = ?,
                           match_reference_embedding_id = ?,
                           match_reference_score = ?,
                           match_cross_area = ?,
                           artifact_dir = ?,
                           preview_filename = ?
                       WHERE id = ?""",
                    (
                        "repeat_capture",
                        now_str,
                        json.dumps({"linkage": linkage, "species_slug": species_slug}, ensure_ascii=False),
                        scoring.top1_fish_id if scoring else None,
                        pipeline_result.reference_sighting_id,
                        pipeline_result.reference_embedding_id,
                        round(pipeline_result.reference_score, 4) if pipeline_result.reference_score else None,
                        1 if pipeline_result.cross_area else 0,
                        review_artifact_dir,
                        review_preview,
                        job_id,
                    ),
                )
                conn.commit()

                logger.info(
                    f"[Job {job_id}] REPEAT CAPTURE (score={match_confidence:.4f}, "
                    f"margin={match_margin:.4f}) — quality too low. "
                    f"No individual or sighting created."
                )

                _emit_progress(job_id, "repeat_capture", 100, "Repeat capture — quality too low")

                return {
                    "status": "repeat_capture",
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
                    "requires_human_review": False,
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

            # Build similarity reference for the definitive case
            similarity_reference = _build_similarity_reference(
                pipeline_result, scoring, cursor, pipeline_decision,
            )
            linkage["similarity_reference"] = similarity_reference

            # Build document schema exactly as requested
            document = {
                "schema_version": "1.1",
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
                "processing_stats": processing_stats,
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
                "processing_stats": processing_stats,
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
                    previous_sighting_id, total_sightings_before, total_sightings_after, linkage_json,
                    match_reference_fish_id, match_reference_sighting_id, match_reference_embedding_id,
                    match_reference_score, match_cross_area
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    json.dumps(linkage, ensure_ascii=False),
                    scoring.top1_fish_id if scoring else None,
                    pipeline_result.reference_sighting_id,
                    pipeline_result.reference_embedding_id,
                    round(pipeline_result.reference_score, 4) if pipeline_result.reference_score else None,
                    1 if pipeline_result.cross_area else 0,
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
            verification_status = "anchor_new" if is_new_fish else "auto_match_unverified"
            matching.store_embedding(
                fish_id=fish_id,
                embedding=embedding_vector,
                species_slug=species_slug,
                area_code=area_code_clean,
                sighting_id=sighting_id,
                latitude=job_doc.get("latitude"),
                longitude=job_doc.get("longitude"),
                verification_status=verification_status,
            )

            # Update identification_jobs final status
            cursor.execute(
                """UPDATE identification_jobs 
                   SET status = ?, completed_at = ?, result_sighting_id = ?, result_fish_id = ?, 
                       confidence = ?, species_slug = ?, is_new_fish = ?, xp_earned = ?, error_message = NULL,
                       artifact_dir = ?, document_filename = ?, preview_filename = ?, annotated_preview_filename = ?,
                       video_filename = ?, rarity = ?, detection_confidence = ?, classification_confidence = ?,
                       match_confidence = ?, catch_number = ?, linked_fish_id = ?, previous_sighting_id = ?,
                       total_sightings_before = ?, total_sightings_after = ?, linkage_json = ?,
                       match_reference_fish_id = ?, match_reference_sighting_id = ?,
                       match_reference_embedding_id = ?, match_reference_score = ?, match_cross_area = ?
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
                    scoring.top1_fish_id if scoring else None,
                    pipeline_result.reference_sighting_id,
                    pipeline_result.reference_embedding_id,
                    round(pipeline_result.reference_score, 4) if pipeline_result.reference_score else None,
                    1 if pipeline_result.cross_area else 0,
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
