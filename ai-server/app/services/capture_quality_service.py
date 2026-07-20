"""
Capture Quality Service for FishDex.

Evaluates whether a capture is suitable for reliable identification.
Produces a quality score and individual metrics.
"""
from dataclasses import dataclass
from typing import Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)

# --- Thresholds ---
MIN_QUALITY_FOR_AUTO_MATCH = 0.6
MIN_QUALITY_FOR_NEW_FISH = 0.4
MIN_CROPS_FOR_AUTO_MATCH = 5


@dataclass(frozen=True)
class CaptureQuality:
    """Quality assessment of a capture."""

    overall_score: float  # 0.0-1.0
    valid_crop_count: int
    detection_confidence_mean: float
    detection_confidence_min: float
    sharpness_mean: float
    crop_pixel_area_mean: float
    border_clipping_ratio: float  # fraction of crops touching frame border
    temporal_coverage: float  # fraction of video duration covered
    duplicate_frame_ratio: float  # fraction of near-duplicate frames
    # Thresholds
    is_acceptable: bool
    rejection_reasons: list[str]


# --- Default scoring weights ---
_DEFAULT_WEIGHTS = {
    "sharpness": 0.25,
    "confidence": 0.25,
    "crop_area": 0.15,
    "border_clipping": 0.10,
    "temporal_coverage": 0.10,
    "duplicate_penalty": 0.15,
}


def _compute_sharpness(frame: np.ndarray) -> float:
    """Compute sharpness via Laplacian variance (grayscale).

    Higher values indicate sharper images. Works on grayscale or BGR/RGB frames.
    """
    if frame is None or frame.size == 0:
        return 0.0

    # Convert to grayscale if needed
    if frame.ndim == 3:
        # Use luminance formula (works for both RGB and BGR)
        gray = np.mean(frame, axis=2).astype(np.float64)
    else:
        gray = frame.astype(np.float64)

    # 3x3 Laplacian kernel
    laplacian_kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)

    # Manual 2D convolution (avoid cv2 dependency)
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0

    # Pad the image
    padded = np.pad(gray, 1, mode="edge")
    laplacian = np.zeros_like(gray)
    for i in range(3):
        for j in range(3):
            laplacian += padded[i : i + h, j : j + w] * laplacian_kernel[i, j]

    return float(np.var(laplacian))


def _is_border_clipping(
    bbox: list, frame_width: int, frame_height: int, margin: int = 5
) -> bool:
    """Check if a detection bbox is within `margin` pixels of the frame edge.

    Args:
        bbox: [x, y, w, h] format.
        frame_width: Width of the source frame.
        frame_height: Height of the source frame.
        margin: Pixel distance to consider as border clipping.

    Returns:
        True if any edge of the bbox is within margin of the frame border.
    """
    x, y, w, h = bbox
    x2 = x + w
    y2 = y + h
    return (
        x <= margin
        or y <= margin
        or x2 >= frame_width - margin
        or y2 >= frame_height - margin
    )


def _compute_histogram(frame: np.ndarray, bins: int = 64) -> np.ndarray:
    """Compute a normalized color histogram for duplicate detection."""
    if frame.ndim == 3:
        # Flatten all channels into a single histogram
        hist, _ = np.histogram(frame.ravel(), bins=bins, range=(0, 256))
    else:
        hist, _ = np.histogram(frame.ravel(), bins=bins, range=(0, 256))
    norm = np.linalg.norm(hist)
    if norm == 0:
        return hist.astype(np.float64)
    return hist.astype(np.float64) / norm


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _compute_duplicate_ratio(
    frames: list[np.ndarray], threshold: float = 0.98
) -> float:
    """Compute fraction of consecutive frame pairs that are near-duplicates.

    Uses cosine similarity on color histograms.
    """
    if len(frames) < 2:
        return 0.0

    histograms = [_compute_histogram(f) for f in frames]
    duplicate_count = 0

    for i in range(len(histograms) - 1):
        sim = _cosine_similarity(histograms[i], histograms[i + 1])
        if sim > threshold:
            duplicate_count += 1

    return duplicate_count / (len(frames) - 1)


def _normalize_sharpness(sharpness: float) -> float:
    """Normalize raw sharpness to 0-1 scale.

    Empirically, Laplacian variance:
      < 50: very blurry
      50-200: acceptable
      > 500: very sharp
    """
    # Sigmoid-like mapping
    return float(min(1.0, sharpness / 500.0))


def _normalize_crop_area(area: float) -> float:
    """Normalize crop pixel area to 0-1 scale.

    Target: >= 50000 px (e.g., ~224x224) is considered good.
    """
    target = 50000.0
    return float(min(1.0, area / target))


def evaluate_capture(
    cropped_frames: list[np.ndarray],
    detections: list[dict],
    video_duration_seconds: float = 0,
    frame_timestamps: list[float] | None = None,
    weights: dict[str, float] | None = None,
) -> CaptureQuality:
    """Evaluate the quality of a fish capture.

    Args:
        cropped_frames: List of cropped frame arrays (RGB or BGR, uint8).
        detections: List of detection dicts, each with at minimum:
            - "bbox": [x, y, w, h]
            - "confidence": float
            - Optionally "frame_width" and "frame_height" for border check.
        video_duration_seconds: Total video duration for temporal coverage.
        frame_timestamps: Timestamps (seconds) for each frame/detection.
        weights: Optional override for scoring weights.

    Returns:
        CaptureQuality dataclass with metrics and acceptability verdict.
    """
    rejection_reasons: list[str] = []
    w = weights if weights is not None else _DEFAULT_WEIGHTS

    # --- Handle empty inputs ---
    if not cropped_frames or not detections:
        logger.warning("evaluate_capture called with empty frames or detections")
        return CaptureQuality(
            overall_score=0.0,
            valid_crop_count=0,
            detection_confidence_mean=0.0,
            detection_confidence_min=0.0,
            sharpness_mean=0.0,
            crop_pixel_area_mean=0.0,
            border_clipping_ratio=0.0,
            temporal_coverage=0.0,
            duplicate_frame_ratio=0.0,
            is_acceptable=False,
            rejection_reasons=["No frames or detections provided"],
        )

    valid_crop_count = len(cropped_frames)

    # --- Detection confidence ---
    confidences = [d.get("confidence", 0.0) for d in detections]
    confidence_mean = float(np.mean(confidences)) if confidences else 0.0
    confidence_min = float(np.min(confidences)) if confidences else 0.0

    # --- Sharpness ---
    sharpness_values = [_compute_sharpness(f) for f in cropped_frames]
    sharpness_mean = float(np.mean(sharpness_values)) if sharpness_values else 0.0

    # --- Crop pixel area ---
    crop_areas = []
    for f in cropped_frames:
        if f is not None and f.size > 0:
            h, ww = f.shape[:2]
            crop_areas.append(float(h * ww))
        else:
            crop_areas.append(0.0)
    crop_pixel_area_mean = float(np.mean(crop_areas)) if crop_areas else 0.0

    # --- Border clipping ---
    border_clip_count = 0
    for d in detections:
        bbox = d.get("bbox")
        frame_w = d.get("frame_width", 0)
        frame_h = d.get("frame_height", 0)
        if bbox and frame_w > 0 and frame_h > 0:
            if _is_border_clipping(bbox, frame_w, frame_h):
                border_clip_count += 1
    border_clipping_ratio = (
        border_clip_count / len(detections) if detections else 0.0
    )

    # --- Temporal coverage ---
    temporal_coverage = 0.0
    if frame_timestamps and len(frame_timestamps) >= 2 and video_duration_seconds > 0:
        ts_sorted = sorted(frame_timestamps)
        span = ts_sorted[-1] - ts_sorted[0]
        temporal_coverage = min(1.0, span / video_duration_seconds)
    elif len(cropped_frames) == 1:
        # Single frame: no temporal info
        temporal_coverage = 0.0

    # --- Duplicate frame ratio ---
    duplicate_frame_ratio = _compute_duplicate_ratio(cropped_frames)

    # --- Overall score computation ---
    norm_sharpness = _normalize_sharpness(sharpness_mean)
    norm_confidence = confidence_mean  # already 0-1
    norm_area = _normalize_crop_area(crop_pixel_area_mean)
    norm_border = 1.0 - border_clipping_ratio  # less clipping = better
    norm_temporal = temporal_coverage
    norm_duplicate = 1.0 - duplicate_frame_ratio  # fewer duplicates = better

    overall_score = (
        w.get("sharpness", 0.25) * norm_sharpness
        + w.get("confidence", 0.25) * norm_confidence
        + w.get("crop_area", 0.15) * norm_area
        + w.get("border_clipping", 0.10) * norm_border
        + w.get("temporal_coverage", 0.10) * norm_temporal
        + w.get("duplicate_penalty", 0.15) * norm_duplicate
    )
    overall_score = float(np.clip(overall_score, 0.0, 1.0))

    # --- Acceptability check ---
    if valid_crop_count < 3:
        rejection_reasons.append(
            f"Insufficient crops: {valid_crop_count} < 3 required"
        )
    if overall_score < MIN_QUALITY_FOR_NEW_FISH:
        rejection_reasons.append(
            f"Overall score {overall_score:.3f} below minimum {MIN_QUALITY_FOR_NEW_FISH}"
        )
    if confidence_min < 0.1:
        rejection_reasons.append(
            f"Minimum detection confidence too low: {confidence_min:.3f}"
        )
    if duplicate_frame_ratio > 0.8:
        rejection_reasons.append(
            f"Too many duplicate frames: {duplicate_frame_ratio:.1%}"
        )

    is_acceptable = overall_score >= MIN_QUALITY_FOR_NEW_FISH and valid_crop_count >= 3

    return CaptureQuality(
        overall_score=overall_score,
        valid_crop_count=valid_crop_count,
        detection_confidence_mean=confidence_mean,
        detection_confidence_min=confidence_min,
        sharpness_mean=sharpness_mean,
        crop_pixel_area_mean=crop_pixel_area_mean,
        border_clipping_ratio=border_clipping_ratio,
        temporal_coverage=temporal_coverage,
        duplicate_frame_ratio=duplicate_frame_ratio,
        is_acceptable=is_acceptable,
        rejection_reasons=rejection_reasons,
    )
