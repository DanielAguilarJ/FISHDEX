"""
Dataset preparer for A/B evaluation and threshold calibration.

Parses calib_data/ directory containing pez_XX_toma_Y folders,
extracts fish OBB crops from video files (.temp / .mp4) or images (.jpg),
and generates eval_data/ dataset directory + manifest.json.

Usage:
    python scripts/prepare_eval_dataset.py \
      --input-dir calib_data/ \
      --output-dir eval_data/ \
      --species cyprinus_carpio \
      --max-frames-per-video 10
"""

import argparse
import json
import logging
import os
import re
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def extract_crops_from_video(
    video_path: Path,
    detector,
    max_frames: int = 10,
) -> list[np.ndarray]:
    """Extract up to max_frames OBB crops of fish from a video file."""
    from app.utils.crop_utils import crop_obb_rotated

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Failed to open video: %s", video_path)
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 100  # fallback

    # Sample uniformly across video
    step = max(1, total_frames // (max_frames * 2))

    crops: list[np.ndarray] = []
    frame_idx = 0

    while cap.isOpened() and len(crops) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % step == 0:
            dets = detector.detect(frame)
            if dets:
                best_det = max(dets, key=lambda d: d.confidence)
                if best_det.confidence >= 0.35:
                    crop = crop_obb_rotated(frame, best_det, pad_frac=0.01)
                    if crop is not None and crop.size > 0:
                        crops.append(crop)

        frame_idx += 1

    cap.release()
    return crops


def extract_crop_from_image(img_path: Path, detector) -> np.ndarray | None:
    """Extract single fish OBB crop from an image file."""
    from app.utils.crop_utils import crop_obb_rotated

    img = cv2.imread(str(img_path))
    if img is None:
        return None

    dets = detector.detect(img)
    if dets:
        best_det = max(dets, key=lambda d: d.confidence)
        crop = crop_obb_rotated(img, best_det, pad_frac=0.01)
        if crop is not None and crop.size > 0:
            return crop

    # Fallback: if detector fails on image, return full image
    return img


def parse_folder_name(folder_name: str) -> tuple[str, str] | None:
    """Parse pez_01_toma_a into ('pez_01', 'session_a')."""
    m = re.match(r"(pez_\d+)_(toma_[abAB])", folder_name, re.IGNORECASE)
    if m:
        fish_id = m.group(1).lower()
        session_id = m.group(2).lower()
        return fish_id, session_id
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Prepare evaluation dataset from calib_data/"
    )
    parser.add_argument("--input-dir", default="calib_data/")
    parser.add_argument("--output-dir", default="eval_data/")
    parser.add_argument("--species", default="cyprinus_carpio")
    parser.add_argument("--max-frames-per-video", type=int, default=10)
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)

    if not input_path.exists():
        logger.error("Input directory does not exist: %s", input_path)
        return

    from app.services.detector_service import get_detector_service
    detector = get_detector_service()

    manifest: list[dict] = []
    processed_count = 0

    subdirs = sorted([d for d in input_path.iterdir() if d.is_dir()])
    logger.info("Found %d subdirectories in %s", len(subdirs), input_path)

    for subdir in subdirs:
        parsed = parse_folder_name(subdir.name)
        if not parsed:
            logger.warning("Skipping unrecognized folder name: %s", subdir.name)
            continue

        fish_id, session_id = parsed
        capture_id = f"{fish_id}_{session_id}"

        target_dir = output_path / args.species / fish_id / session_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # Look for video file (.temp or .mp4)
        video_files = list(subdir.glob("*.temp")) + list(subdir.glob("*.mp4"))
        image_files = list(subdir.glob("*.jpg")) + list(subdir.glob("*.png"))

        crops: list[np.ndarray] = []

        if video_files:
            logger.info("Processing video %s for %s/%s", video_files[0].name, fish_id, session_id)
            crops = extract_crops_from_video(video_files[0], detector, max_frames=args.max_frames_per_video)

        if not crops and image_files:
            logger.info("Processing image %s for %s/%s", image_files[0].name, fish_id, session_id)
            crop = extract_crop_from_image(image_files[0], detector)
            if crop is not None:
                crops.append(crop)

        if not crops:
            logger.warning("No crops extracted for %s/%s", fish_id, session_id)
            continue

        for idx, crop in enumerate(crops, 1):
            roi_filename = f"roi_{idx:03d}.jpg"
            roi_path = target_dir / roi_filename
            cv2.imwrite(str(roi_path), crop)

            manifest.append({
                "path": str(roi_path).replace("\\", "/"),
                "species_slug": args.species,
                "fish_id": fish_id,
                "session_id": session_id,
                "capture_id": capture_id,
            })

        processed_count += 1
        logger.info("  -> Saved %d crops to %s", len(crops), target_dir)

    manifest_path = output_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info("=" * 60)
    logger.info("Dataset preparation complete!")
    logger.info("Total folders processed: %d", processed_count)
    logger.info("Total ROIs saved:       %d", len(manifest))
    logger.info("Manifest saved to:      %s", manifest_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
