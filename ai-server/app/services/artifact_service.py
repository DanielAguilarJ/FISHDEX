import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
import logging
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def _write_jpg(path: Path, image: np.ndarray, quality: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    q = quality if quality is not None else (settings.jpeg_quality or 90)
    ok = cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        raise RuntimeError(f"Failed to write image: {path}")


def _storage_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return "/storage/" + relative_path.replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _draw_annotated_frame(
    frame: np.ndarray,
    detection,
    species_english: Optional[str],
    fish_id: str,
    catch_number: int,
    detection_conf: float,
    classification_conf: float,
    match_conf: float,
    is_new_fish: bool,
    model_type: str = "yolov8_obb",
) -> np.ndarray:
    """
    Draw detection polygon/bbox and AI validation labels on a copy of the frame.
    Returns an annotated BGR image ready to save as JPEG.
    """
    img = frame.copy()
    h, w = img.shape[:2]

    # --- Extraction of bbox / polygon from detection object ---
    polygon: list | None = None
    bbox: tuple | None = None
    if detection is not None:
        if isinstance(detection, dict):
            polygon = detection.get("polygon")
            bbox = detection.get("bbox_xyxy") or detection.get("bbox")
        else:
            polygon = getattr(detection, "polygon", None)
            bbox = getattr(detection, "bbox_xyxy", None)

    box_color = (30, 230, 110) if not is_new_fish else (30, 210, 255)  # BGR green / cyan

    # --- Draw bounding polygon or rectangle ---
    if polygon and len(polygon) >= 3:
        pts = np.array([[int(p[0]), int(p[1])] for p in polygon], dtype=np.int32)
        # Thin semi-transparent fill
        fill_ov = img.copy()
        cv2.fillPoly(fill_ov, [pts], box_color)
        cv2.addWeighted(fill_ov, 0.08, img, 0.92, 0, img)
        # Solid outline
        cv2.polylines(img, [pts], True, box_color, 3)
    elif bbox and len(bbox) >= 4:
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))
        if x2 > x1 and y2 > y1:
            cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 3)

    # --- Label block (top-left) ---
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.40, min(0.72, w / 950))
    thick = max(1, int(scale * 2))
    line_h = int(28 * scale)
    pad = 8

    # Each line: (text, BGR color)
    lines: list[tuple[str, tuple]] = [
        ((species_english or "Unknown").upper(), (220, 235, 255)),  # light blue-white
        (f"#{fish_id}   CATCH {catch_number}", (165, 165, 165)),    # gray
        (f"DET   {detection_conf:.1%}", (80, 230, 80)),             # green
        (f"CLS   {classification_conf:.1%}", (255, 200, 80)),       # blue-cyan
    ]
    if is_new_fish:
        lines.append(("[ NEW FISH ]", (80, 255, 180)))
    else:
        lines.append((f"MATCH {match_conf:.1%}", (80, 175, 255)))   # orange
    lines.append((model_type.upper(), (140, 130, 185)))              # dim purple

    # Measure widest line
    max_tw = max(
        cv2.getTextSize(t, font, scale, thick)[0][0] for t, _ in lines
    )
    block_w = max_tw + pad * 2
    block_h = len(lines) * line_h + pad * 2
    lx, ly = 8, 8

    # Semi-transparent dark background
    bg_ov = img.copy()
    cv2.rectangle(bg_ov, (lx, ly), (lx + block_w, ly + block_h), (10, 10, 14), -1)
    cv2.addWeighted(bg_ov, 0.82, img, 0.18, 0, img)

    for i, (text, color) in enumerate(lines):
        ty = ly + pad + (i + 1) * line_h - 4
        cv2.putText(img, text, (lx + pad, ty), font, scale, color, thick, cv2.LINE_AA)

    # --- Top-right AI confidence badge ---
    overall = max(detection_conf, classification_conf)
    badge_text = f"{overall:.0%} AI"
    (bw, bh), _ = cv2.getTextSize(badge_text, font, scale, thick)
    bx = w - bw - pad * 2 - 8
    by_top = 8
    by_bot = by_top + bh + pad * 2

    badge_ov = img.copy()
    cv2.rectangle(badge_ov, (bx - pad, by_top), (bx + bw + pad, by_bot), (10, 10, 14), -1)
    cv2.addWeighted(badge_ov, 0.82, img, 0.18, 0, img)
    badge_color = (80, 230, 80) if overall >= 0.70 else (80, 100, 210)
    cv2.putText(img, badge_text, (bx, by_bot - pad), font, scale, badge_color, thick, cv2.LINE_AA)

    return img


def save_job_artifacts(
    job_id: str,
    selected_frames: list[np.ndarray],
    cropped_frames: list[np.ndarray],
    raw_video_path: str,
) -> dict:
    """
    Saves temporary artifacts associated with a job (selected frames, crops, preview).
    Returns relative paths and public storage URLs.
    """
    base = Path(settings.job_artifacts_dir) / job_id
    selected_dir = base / "selected_frames"  # noqa: F841
    crops_dir = base / "crops"               # noqa: F841

    selected_files = []
    for i, frame in enumerate(selected_frames):
        rel = f"jobs/{job_id}/selected_frames/frame_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, frame)
        selected_files.append(rel)

    crop_files = []
    for i, crop in enumerate(cropped_frames):
        rel = f"jobs/{job_id}/crops/crop_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, crop)
        crop_files.append(rel)

    preview_filename = crop_files[0] if crop_files else (selected_files[0] if selected_files else None)

    if preview_filename:
        preview_abs_source = Path(settings.server_data_dir) / "storage" / preview_filename
        preview_rel = f"jobs/{job_id}/preview.jpg"
        preview_abs = Path(settings.server_data_dir) / "storage" / preview_rel
        preview_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(preview_abs_source, preview_abs)
        preview_filename = preview_rel

    return {
        "job_artifact_dir": f"jobs/{job_id}",
        "preview_filename": preview_filename,
        "preview_url": _storage_url(preview_filename),
        "selected_frame_files": selected_files,
        "selected_frame_urls": [_storage_url(p) for p in selected_files],
        "crop_files": crop_files,
        "crop_urls": [_storage_url(p) for p in crop_files],
    }


from app.utils.area_utils import normalize_area_code
from app.utils.crop_utils import crop_obb_rotated, crop_bbox_aligned_strict


def save_fish_capture_artifacts(
    job_id: str,
    sighting_id: str,
    area_code: str,
    species_slug: str,
    fish_id: str,
    catch_number: int,
    selected_frames: list[np.ndarray],
    cropped_frames: list[np.ndarray],          # OBB-rotated crops (primary)
    raw_video_path: str,
    document: dict,
    model_outputs: dict,
    media_type: str = "video",
    is_new_fish: bool = True,
    linkage: dict | None = None,
    # --- Annotation / dataset params ---
    best_detection_frame: Optional[np.ndarray] = None,
    best_detection=None,
    species_english: Optional[str] = None,
    detection_confidence: float = 0.0,
    classification_confidence: float = 0.0,
    match_confidence: float = 0.0,
    model_type: str = "yolov8_obb",
    all_dataset_detections: Optional[list] = None,  # list of (frame, detection, conf)
    cropped_frames_bbox: Optional[list[np.ndarray]] = None,  # axis-aligned crops
) -> dict:
    """
    Saves final artifacts for a fish capture sighting.

    Public media goes to  storage/fish_media/{area}/{species}/{fish_id}/catch_{N}_{job_id}/
    Private metadata goes to private/fish_documents/{area}/{species}/{fish_id}/catch_{N}_{job_id}/

    New in this version:
    - annotated_preview.jpg  : best_detection_frame with bbox + AI labels drawn on it
    - dataset/crop_NNN.jpg   : tight fish crops from ALL detected frames (training data)
    - annotated/frame_NNN.jpg: full frames with bbox + AI labels for every dataset detection
    """
    area_clean = normalize_area_code(area_code)
    safe_species = species_slug or "unknown_species"

    rel_base = (
        f"fish_media/{area_clean}/{safe_species}/{fish_id}/"
        f"catch_{catch_number}_{job_id}"
    )

    abs_base = Path(settings.server_data_dir) / "storage" / rel_base
    images_dir = abs_base / "images"
    images_bbox_dir = abs_base / "images_bbox"
    frames_dir = abs_base / "frames"
    raw_dir = abs_base / "raw"
    dataset_dir = abs_base / "dataset"
    annotated_dir = abs_base / "annotated"

    for d in (images_dir, images_bbox_dir, frames_dir, raw_dir, dataset_dir, annotated_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ── OBB-rotated crops (primary — used for embedding + preview) ─────────
    image_files = []
    for i, crop in enumerate(cropped_frames):
        rel = f"{rel_base}/images/crop_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, crop)
        image_files.append(rel)

    # ── Axis-aligned bbox crops (secondary — training diversity) ───────────
    image_bbox_files: list[str] = []
    if cropped_frames_bbox:
        for i, crop in enumerate(cropped_frames_bbox):
            rel = f"{rel_base}/images_bbox/crop_{i:02d}.jpg"
            abs_path = Path(settings.server_data_dir) / "storage" / rel
            _write_jpg(abs_path, crop)
            image_bbox_files.append(rel)

    # ── Best-N selected frames ─────────────────────────────────────────────
    frame_files = []
    for i, frame in enumerate(selected_frames):
        rel = f"{rel_base}/frames/frame_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, frame)
        frame_files.append(rel)

    # ── Plain preview = first OBB crop (clean, no labels) ────────────────
    #   This is what the phone displays. Only created if a valid crop exists.
    preview_filename: str | None = None
    if image_files:
        preview_filename = f"{rel_base}/preview.jpg"
        preview_abs = Path(settings.server_data_dir) / "storage" / preview_filename
        preview_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            Path(settings.server_data_dir) / "storage" / image_files[0],
            preview_abs,
        )
    # NOTE: If cropped_frames was empty, images/ will be empty and NO preview.jpg
    # is created. The phone will show the frame as a temporary placeholder.

    # ── Annotated preview ─────────────────────────────────────────────────
    #   Best detection frame with OBB polygon + AI label block drawn on it.
    annotated_preview_filename: str | None = None
    ann_source_frame = best_detection_frame if best_detection_frame is not None else (
        selected_frames[0] if selected_frames else None
    )
    if ann_source_frame is not None:
        try:
            annotated_img = _draw_annotated_frame(
                frame=ann_source_frame,
                detection=best_detection,
                species_english=species_english,
                fish_id=fish_id,
                catch_number=catch_number,
                detection_conf=detection_confidence,
                classification_conf=classification_confidence,
                match_conf=match_confidence,
                is_new_fish=is_new_fish,
                model_type=model_type,
            )
            annotated_preview_filename = f"{rel_base}/annotated_preview.jpg"
            ann_abs = Path(settings.server_data_dir) / "storage" / annotated_preview_filename
            _write_jpg(ann_abs, annotated_img, quality=78)
            logger.info(f"Saved annotated preview: {annotated_preview_filename}")
        except Exception as ann_err:
            logger.warning(f"Failed to generate annotated preview: {ann_err}")
            annotated_preview_filename = None

    # ── Dataset crops + annotated full frames from ALL detected frames ─────
    #   all_dataset_detections: list of (frame, detection, confidence)
    #   For each detected frame we save:
    #     dataset/crop_NNN.jpg        ← OBB-rotated (fish body horizontal)
    #     dataset/crop_NNN_bbox.jpg   ← axis-aligned bbox (traditional rect crop)
    #     annotated/frame_NNN.jpg     ← full frame with OBB polygon + AI labels
    dataset_crop_files: list[str] = []
    dataset_bbox_files: list[str] = []
    annotated_frame_files: list[str] = []

    if all_dataset_detections:
        for idx, (d_frame, d_det, d_conf) in enumerate(all_dataset_detections):
            try:
                # --- OBB-rotated crop ---
                obb_crop = crop_obb_rotated(d_frame, d_det)
                if obb_crop is None or obb_crop.size == 0:
                    obb_crop = crop_bbox_aligned(d_frame, d_det)
                crop_rel = f"{rel_base}/dataset/crop_{idx:03d}.jpg"
                crop_abs = Path(settings.server_data_dir) / "storage" / crop_rel
                _write_jpg(crop_abs, obb_crop)
                dataset_crop_files.append(crop_rel)

                # --- Axis-aligned bbox crop ---
                bbox_crop = crop_bbox_aligned_strict(d_frame, d_det)
                if bbox_crop is not None:
                    bbox_rel = f"{rel_base}/dataset/crop_{idx:03d}_bbox.jpg"
                    bbox_abs = Path(settings.server_data_dir) / "storage" / bbox_rel
                    _write_jpg(bbox_abs, bbox_crop)
                    dataset_bbox_files.append(bbox_rel)

                # --- Annotated full frame ---
                ann_rel = f"{rel_base}/annotated/frame_{idx:03d}.jpg"
                ann_abs_path = Path(settings.server_data_dir) / "storage" / ann_rel
                ann_f = _draw_annotated_frame(
                    frame=d_frame,
                    detection=d_det,
                    species_english=species_english,
                    fish_id=fish_id,
                    catch_number=catch_number,
                    detection_conf=d_conf,
                    classification_conf=classification_confidence,
                    match_conf=match_confidence,
                    is_new_fish=is_new_fish,
                    model_type=model_type,
                )
                _write_jpg(ann_abs_path, ann_f, quality=78)
                annotated_frame_files.append(ann_rel)
            except Exception as ds_err:
                logger.warning(f"Dataset frame {idx} failed: {ds_err}")

        logger.info(
            f"Saved {len(dataset_crop_files)} OBB crops, "
            f"{len(dataset_bbox_files)} bbox crops, "
            f"{len(annotated_frame_files)} annotated frames"
        )

    # ── Raw video / photo copy ─────────────────────────────────────────────
    video_filename: str | None = None
    raw_filename: str | None = None

    if raw_video_path and Path(raw_video_path).exists():
        raw_ext = Path(raw_video_path).suffix.lower()
        if not raw_ext:
            raw_ext = ".jpg" if media_type == "image" else ".mp4"

        raw_filename = f"{rel_base}/raw/raw_capture{raw_ext}"
        raw_abs = Path(settings.server_data_dir) / "storage" / raw_filename
        raw_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_video_path, raw_abs)

        if media_type == "video":
            video_filename = raw_filename

    # ── Private metadata documents ─────────────────────────────────────────
    private_rel_base = (
        f"fish_documents/{area_clean}/{safe_species}/{fish_id}/"
        f"catch_{catch_number}_{job_id}"
    )

    document_dir = Path(settings.private_data_dir) / private_rel_base
    document_dir.mkdir(parents=True, exist_ok=True)

    document_filename = f"{private_rel_base}/document.json"
    manifest_filename = f"{private_rel_base}/manifest.json"
    model_outputs_filename = f"{private_rel_base}/model_outputs.json"
    fish_index_filename = f"fish_documents/{area_clean}/{safe_species}/{fish_id}/fish_index.json"

    media = {
        "media_type": media_type,
        "preview": _storage_url(preview_filename),
        "annotated_preview": _storage_url(annotated_preview_filename),
        "raw": _storage_url(raw_filename),
        "video": _storage_url(video_filename),
        "images": [_storage_url(p) for p in image_files],
        "images_bbox": [_storage_url(p) for p in image_bbox_files],
        "frames": [_storage_url(p) for p in frame_files],
        "dataset_crops": [_storage_url(p) for p in dataset_crop_files],
        "dataset_crops_bbox": [_storage_url(p) for p in dataset_bbox_files],
        "annotated_frames": [_storage_url(p) for p in annotated_frame_files],
    }

    # Populate document media and linkage
    document["media"] = media
    document["linkage"] = linkage or {}
    document["storage"] = {
        "public_artifact_dir": rel_base,
        "private_document_dir": private_rel_base,
        "document_filename": document_filename,
        "manifest_filename": manifest_filename,
        "model_outputs_filename": model_outputs_filename,
        "fish_index_filename": fish_index_filename,
    }

    manifest = {
        "schema_version": "1.1",
        "job_id": job_id,
        "sighting_id": sighting_id,
        "fish_id": fish_id,
        "area_code": area_clean,
        "species_slug": safe_species,
        "catch_number": catch_number,
        "is_new_fish": is_new_fish,
        "artifact_dir": rel_base,
        "private_document_dir": private_rel_base,
        "created_at": _now_iso(),
        "files": {
            "preview": preview_filename,
            "annotated_preview": annotated_preview_filename,
            "raw": raw_filename,
            "video": video_filename,
            "images": image_files,
            "images_bbox": image_bbox_files,
            "frames": frame_files,
            "dataset_crops": dataset_crop_files,
            "dataset_crops_bbox": dataset_bbox_files,
            "annotated_frames": annotated_frame_files,
            "document": document_filename,
            "manifest": manifest_filename,
            "model_outputs": model_outputs_filename,
            "fish_index": fish_index_filename,
        },
        "urls": media,
        "linkage": linkage or {},
    }

    # Write private JSON files
    (document_dir / "document.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (document_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (document_dir / "model_outputs.json").write_text(
        json.dumps(model_outputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Saved fish capture artifacts under: {rel_base}")

    return {
        "artifact_dir": rel_base,
        "artifact_abs_dir": abs_base,
        "private_abs_dir": document_dir,
        "preview_filename": preview_filename,
        "preview_url": _storage_url(preview_filename),
        "annotated_preview_filename": annotated_preview_filename,
        "annotated_preview_url": _storage_url(annotated_preview_filename),
        "document_filename": document_filename,
        "manifest_filename": manifest_filename,
        "model_outputs_filename": model_outputs_filename,
        "fish_index_filename": fish_index_filename,
        "image_files": image_files,
        "image_bbox_files": image_bbox_files,
        "frame_files": frame_files,
        "dataset_crop_files": dataset_crop_files,
        "dataset_bbox_files": dataset_bbox_files,
        "annotated_frame_files": annotated_frame_files,
        "video_filename": video_filename,
        "raw_filename": raw_filename,
        "media": media,
        "manifest": manifest,
    }


def update_fish_index_file(index_path: Path, entry: dict) -> None:
    """
    Safely creates or appends an entry to the fish_index.json summary file.
    Runs post-commit to prevent index pollution on DB transaction rollbacks.
    """
    index_path.parent.mkdir(parents=True, exist_ok=True)

    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    else:
        existing = {}

    captures = existing.get("captures", [])

    # Prevent duplicate records if job is re-run
    captures = [c for c in captures if c.get("job_id") != entry.get("job_id")]
    captures.append(entry)
    captures.sort(key=lambda x: x.get("catch_number", 0))

    index_doc = {
        "schema_version": "1.0",
        "fish_id": entry.get("fish_id"),
        "area_code": entry.get("area_code"),
        "species_slug": entry.get("species_slug"),
        "total_captures": len(captures),
        "updated_at": _now_iso(),
        "captures": captures,
    }

    index_path.write_text(
        json.dumps(index_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"Updated fish index file at: {index_path}")
