import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
import logging

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

def _write_jpg(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(
        str(path),
        image,
        [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality or 90],
    )
    if not ok:
        raise RuntimeError(f"Failed to write image: {path}")


def _storage_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return "/storage/" + relative_path.replace("\\", "/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_job_artifacts(
    job_id: str,
    selected_frames: list[np.ndarray],
    cropped_frames: list[np.ndarray],
    raw_video_path: str,
) -> dict:
    """
    Saves temporary artifacts associated with a job (selected frames, crops, and preview).
    Returns relative paths and public storage URLs.
    """
    base = Path(settings.job_artifacts_dir) / job_id
    selected_dir = base / "selected_frames"
    crops_dir = base / "crops"

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

def save_fish_capture_artifacts(
    job_id: str,
    sighting_id: str,
    area_code: str,
    species_slug: str,
    fish_id: str,
    catch_number: int,
    selected_frames: list[np.ndarray],
    cropped_frames: list[np.ndarray],
    raw_video_path: str,
    document: dict,
    model_outputs: dict,
    media_type: str = "video",
    is_new_fish: bool = True,
    linkage: dict | None = None,
) -> dict:
    """
    Saves final artifacts associated with a fish capture sighting.
    Writes public media to storage/fish_media and private metadata JSONs to private/fish_documents.
    """
    area_clean = normalize_area_code(area_code)
    safe_species = species_slug or "unknown_species"

    rel_base = (
        f"fish_media/{area_clean}/{safe_species}/{fish_id}/"
        f"catch_{catch_number}_{job_id}"
    )

    abs_base = Path(settings.server_data_dir) / "storage" / rel_base
    images_dir = abs_base / "images"
    frames_dir = abs_base / "frames"
    raw_dir = abs_base / "raw"

    images_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    image_files = []
    for i, crop in enumerate(cropped_frames):
        rel = f"{rel_base}/images/crop_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, crop)
        image_files.append(rel)

    frame_files = []
    for i, frame in enumerate(selected_frames):
        rel = f"{rel_base}/frames/frame_{i:02d}.jpg"
        abs_path = Path(settings.server_data_dir) / "storage" / rel
        _write_jpg(abs_path, frame)
        frame_files.append(rel)

    preview_filename = None
    if image_files:
        preview_filename = f"{rel_base}/preview.jpg"
        preview_abs = Path(settings.server_data_dir) / "storage" / preview_filename
        preview_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            Path(settings.server_data_dir) / "storage" / image_files[0],
            preview_abs,
        )

    video_filename = None
    raw_filename = None

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
        "raw": _storage_url(raw_filename),
        "video": _storage_url(video_filename),
        "images": [_storage_url(p) for p in image_files],
        "frames": [_storage_url(p) for p in frame_files],
    }

    # Populate document media and linkage URLs
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
        "schema_version": "1.0",
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
            "raw": raw_filename,
            "video": video_filename,
            "images": image_files,
            "frames": frame_files,
            "document": document_filename,
            "manifest": manifest_filename,
            "model_outputs": model_outputs_filename,
            "fish_index": fish_index_filename,
        },
        "urls": media,
        "linkage": linkage or {},
    }

    # Write private JSON documents
    (document_dir / "document.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (document_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (document_dir / "model_outputs.json").write_text(
        json.dumps(model_outputs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(f"Saved fish capture artifacts under: {rel_base}")

    return {
        "artifact_dir": rel_base,
        "artifact_abs_dir": abs_base,
        "private_abs_dir": document_dir,
        "preview_filename": preview_filename,
        "preview_url": _storage_url(preview_filename),
        "document_filename": document_filename,
        "manifest_filename": manifest_filename,
        "model_outputs_filename": model_outputs_filename,
        "fish_index_filename": fish_index_filename,
        "image_files": image_files,
        "frame_files": frame_files,
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
        json.dumps(index_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Updated fish index file at: {index_path}")

