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


def save_fish_capture_artifacts(
    job_id: str,
    area_code: str,
    species_slug: str,
    fish_id: str,
    catch_number: int,
    selected_frames: list[np.ndarray],
    cropped_frames: list[np.ndarray],
    raw_video_path: str,
    document: dict,
    model_outputs: dict,
) -> dict:
    """
    Saves final artifacts associated with a fish capture sighting.
    Writes public media to storage/fish_media and private metadata JSONs to private/fish_documents.
    """
    area_clean = (area_code or "XX").replace(" ", "").replace("-", "").upper()
    safe_species = species_slug or "unknown_species"

    rel_base = (
        f"fish_media/{area_clean}/{safe_species}/{fish_id}/"
        f"catch_{catch_number}_{job_id}"
    )

    abs_base = Path(settings.server_data_dir) / "storage" / rel_base
    images_dir = abs_base / "images"
    frames_dir = abs_base / "frames"
    raw_dir = abs_base / "raw"

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
    if raw_video_path and Path(raw_video_path).exists():
        video_filename = f"{rel_base}/raw/raw_video.mp4"
        video_abs = Path(settings.server_data_dir) / "storage" / video_filename
        video_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_video_path, video_abs)

    document_dir = Path(settings.fish_documents_dir) / job_id
    document_dir.mkdir(parents=True, exist_ok=True)

    document_filename = f"fish_documents/{job_id}/document.json"
    manifest_filename = f"fish_documents/{job_id}/manifest.json"
    model_outputs_filename = f"fish_documents/{job_id}/model_outputs.json"

    media = {
        "preview": _storage_url(preview_filename),
        "video": _storage_url(video_filename),
        "images": [_storage_url(p) for p in image_files],
        "frames": [_storage_url(p) for p in frame_files],
    }

    # Populate document media URLs
    document["media"] = media

    manifest = {
        "schema_version": "1.0",
        "job_id": job_id,
        "fish_id": fish_id,
        "artifact_dir": rel_base,
        "created_at": _now_iso(),
        "files": {
            "preview": preview_filename,
            "video": video_filename,
            "images": image_files,
            "frames": frame_files,
            "document": document_filename,
            "model_outputs": model_outputs_filename,
        },
        "urls": media,
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
        "preview_filename": preview_filename,
        "preview_url": _storage_url(preview_filename),
        "document_filename": document_filename,
        "manifest_filename": manifest_filename,
        "model_outputs_filename": model_outputs_filename,
        "image_files": image_files,
        "frame_files": frame_files,
        "video_filename": video_filename,
        "media": media,
        "manifest": manifest,
    }
