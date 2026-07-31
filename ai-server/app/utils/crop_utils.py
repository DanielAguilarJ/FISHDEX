"""
FishDex AI Server — OBB Crop Utilities
=======================================
Tight fish crops using the OBB polygon from YOLOv8 detection.
NO fallback to center-crop — if there's no valid detection, returns None.

  crop_obb_rotated(frame, detection, pad_frac=0.01)
    Perspective-warps the exact OBB polygon to a tight rectangle.
    Fish body axis → horizontal.  Returns None if polygon unavailable.

  crop_bbox_aligned_strict(frame, detection, pad_frac=0.01)
    Axis-aligned bbox crop. Returns None if no bbox (NO fallback 70%).

  crop_fish_best(frame, detection, pad_frac=0.01)
    Tries OBB first, then bbox_strict. Returns None if neither works.

  get_obb_rectification(detection, pad_frac=0.01)
    Returns OBBRectification with forward/inverse matrices.

  compute_fingerprint_box(width, height, x_start, x_end, y_start, y_end)
    Pure helper: fingerprint bounding box in rectified crop coordinates.

  project_fingerprint_polygon_to_frame(detection, pad_frac, x_start, ...)
    Projects fingerprint rectangle back to original frame coordinates.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Union, runtime_checkable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection shape
# ---------------------------------------------------------------------------
# Detections arrive from two places with the same duck-typed shape:
#   * DetectionResult dataclasses produced by detector_service
#   * plain dicts produced by the tracking and retry paths
# A Protocol documents the contract without forcing either producer to inherit
# from a common base, and the alias keeps the 12 call signatures readable.


@runtime_checkable
class DetectionProtocol(Protocol):
    """Attribute-style detection: an object exposing polygon and bbox."""

    polygon: Optional[list]
    bbox_xyxy: Optional[tuple]


#: Either an object satisfying :class:`DetectionProtocol` or a mapping with
#: ``polygon`` / ``bbox_xyxy`` (or legacy ``bbox``) keys.
DetectionLike = Union[DetectionProtocol, dict[str, Any]]


# ---------------------------------------------------------------------------
# OBBRectification — reusable perspective transform data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OBBRectification:
    """Encapsulates the perspective transform used to rectify an OBB fish crop."""

    src_points: np.ndarray       # (4, 2) float32 — corners in original frame
    dst_points: np.ndarray       # (4, 2) float32 — corners in output rectangle
    matrix: np.ndarray           # 3×3 forward homography (frame → crop)
    inverse_matrix: np.ndarray   # 3×3 inverse homography (crop → frame)
    output_width: int
    output_height: int


def _get_polygon(detection: Optional[DetectionLike]) -> Optional[list]:
    """Extract the OBB polygon corner list from any detection object."""
    if detection is None:
        return None
    if isinstance(detection, dict):
        return detection.get("polygon")
    return getattr(detection, "polygon", None)


def _get_bbox(detection: Optional[DetectionLike]) -> Optional[tuple]:
    """Extract the axis-aligned bbox_xyxy from any detection object."""
    if detection is None:
        return None
    if isinstance(detection, dict):
        return detection.get("bbox_xyxy") or detection.get("bbox")
    return getattr(detection, "bbox_xyxy", None)


def get_obb_rectification(
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
) -> Optional[OBBRectification]:
    """
    Compute the perspective transform that rectifies an OBB polygon to a
    tight horizontal rectangle.  Returns None if polygon is unavailable or
    degenerate.

    The returned OBBRectification contains both forward and inverse matrices,
    allowing projection between frame coordinates and rectified crop coordinates.
    """
    polygon = _get_polygon(detection)
    if polygon is None or len(polygon) < 4:
        return None

    p = [np.array([float(v[0]), float(v[1])], dtype=np.float64) for v in polygon[:4]]

    # Measure both side lengths
    w_side = float(np.linalg.norm(p[1] - p[0]))   # TL → TR
    h_side = float(np.linalg.norm(p[2] - p[1]))   # TR → BR

    if w_side < 4.0 or h_side < 4.0:
        return None  # degenerate

    # Long side → width (fish horizontal)
    if w_side >= h_side:
        src_pts = np.float32([p[0], p[1], p[2], p[3]])
        w_out, h_out = w_side, h_side
    else:
        # Rotate corner assignment so h becomes width
        src_pts = np.float32([p[3], p[0], p[1], p[2]])
        w_out, h_out = h_side, w_side

    # Output dimensions + padding
    pw = w_out * pad_frac
    ph = h_out * pad_frac
    out_w = max(4, int(round(w_out + 2.0 * pw)))
    out_h = max(4, int(round(h_out + 2.0 * ph)))

    dst_pts = np.float32([
        [pw, ph],
        [out_w - pw, ph],
        [out_w - pw, out_h - ph],
        [pw, out_h - ph],
    ])

    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    inverse_matrix = cv2.getPerspectiveTransform(dst_pts, src_pts)

    return OBBRectification(
        src_points=src_pts,
        dst_points=dst_pts,
        matrix=matrix,
        inverse_matrix=inverse_matrix,
        output_width=out_w,
        output_height=out_h,
    )


def crop_obb_rotated(
    frame: np.ndarray,
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
) -> Optional[np.ndarray]:
    """
    Perspective-warp the OBB polygon to a tight rectangular crop.

    Uses the 4 polygon corners directly with cv2.getPerspectiveTransform.
    The long side of the OBB maps to the output width (fish horizontal).
    pad_frac = 1% padding on each side (tight; override to 0.0 for zero margin).

    Returns None if polygon is unavailable or degenerate.
    """
    rect = get_obb_rectification(detection, pad_frac=pad_frac)
    if rect is None:
        return None

    warped = cv2.warpPerspective(
        frame, rect.matrix, (rect.output_width, rect.output_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    if warped is None or warped.size == 0:
        return None

    return warped


def crop_bbox_aligned_strict(
    frame: np.ndarray,
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
) -> Optional[np.ndarray]:
    """
    Axis-aligned bounding-box crop with 1% padding.
    Returns None if no valid bbox is available.
    NO fallback to center crop — strict mode.
    """
    bbox = _get_bbox(detection)
    if not bbox or len(bbox) < 4:
        return None

    h_img, w_img = frame.shape[:2]
    x1_f, y1_f, x2_f, y2_f = (
        float(bbox[0]), float(bbox[1]),
        float(bbox[2]), float(bbox[3]),
    )
    bw = x2_f - x1_f
    bh = y2_f - y1_f

    if bw < 4.0 or bh < 4.0:
        return None

    x1 = max(0, int(x1_f - bw * pad_frac))
    y1 = max(0, int(y1_f - bh * pad_frac))
    x2 = min(w_img, int(x2_f + bw * pad_frac))
    y2 = min(h_img, int(y2_f + bh * pad_frac))

    if x2 <= x1 or y2 <= y1:
        return None

    return frame[y1:y2, x1:x2].copy()


def crop_fish_best(
    frame: np.ndarray,
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
) -> Optional[np.ndarray]:
    """
    Primary crop selector. Returns None if no valid crop is possible.
    Tries OBB perspective warp first, then strict bbox.
    NEVER returns a fallback center crop.
    """
    obb = crop_obb_rotated(frame, detection, pad_frac=pad_frac)
    if obb is not None and obb.size > 0:
        return obb
    return crop_bbox_aligned_strict(frame, detection, pad_frac=pad_frac)


def pad_image_to_aspect(
    image: np.ndarray,
    target_aspect: float,
    fill_color: tuple[int, int, int] = (114, 114, 114),
) -> Optional[np.ndarray]:
    """
    Pads an image to match target_aspect = width / height.
    Does not distort image.
    """
    if image is None or image.size == 0:
        return None

    h, w = image.shape[:2]
    if h <= 0 or w <= 0 or target_aspect <= 0:
        return image

    current_aspect = w / h

    if abs(current_aspect - target_aspect) < 0.01:
        return image

    if current_aspect > target_aspect:
        # Image is too wide; add height.
        new_w = w
        new_h = int(round(w / target_aspect))
    else:
        # Image is too tall; add width.
        new_h = h
        new_w = int(round(h * target_aspect))

    canvas = np.full((new_h, new_w, 3), fill_color, dtype=image.dtype)

    x = (new_w - w) // 2
    y = (new_h - h) // 2

    canvas[y:y + h, x:x + w] = image

    return canvas


def crop_bbox_preserve_frame_aspect(
    frame: np.ndarray,
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
    fill_color: tuple[int, int, int] = (114, 114, 114),
) -> Optional[np.ndarray]:
    """
    Crops fish with axis-aligned bbox, then pads the crop to preserve
    the original frame aspect ratio.
    If frame is vertical, output remains vertical.
    If frame is horizontal, output remains horizontal.
    """
    crop = crop_bbox_aligned_strict(frame, detection, pad_frac=pad_frac)
    if crop is None or crop.size == 0:
        return None

    frame_h, frame_w = frame.shape[:2]
    target_aspect = frame_w / frame_h

    return pad_image_to_aspect(
        crop,
        target_aspect=target_aspect,
        fill_color=fill_color,
    )


# ---------------------------------------------------------------------------
# Fingerprint geometry helpers
# ---------------------------------------------------------------------------


def compute_fingerprint_box(
    width: int,
    height: int,
    x_start: float = 0.20,
    x_end: float = 0.80,
    y_start: float = 0.05,
    y_end: float = 0.55,
) -> tuple[int, int, int, int]:
    """
    Compute the fingerprint bounding box in pixel coordinates within a
    rectified crop of the given dimensions.

    Uses round() — consistent with FishFingerprintCrop in fish_encoder_model.py.
    Returns (x1, y1, x2, y2) clamped so at least 1px in each dimension.
    """
    if not (0.0 <= x_start < x_end <= 1.0):
        raise ValueError(
            f"Expected 0 <= x_start < x_end <= 1, got x_start={x_start}, x_end={x_end}"
        )
    if not (0.0 <= y_start < y_end <= 1.0):
        raise ValueError(
            f"Expected 0 <= y_start < y_end <= 1, got y_start={y_start}, y_end={y_end}"
        )

    x1 = int(round(x_start * width))
    x2 = int(round(x_end * width))
    y1 = int(round(y_start * height))
    y2 = int(round(y_end * height))

    # Clamp to image bounds — same logic as FishFingerprintCrop
    x1 = max(0, min(x1, width - 1))
    x2 = max(x1 + 1, min(x2, width))
    y1 = max(0, min(y1, height - 1))
    y2 = max(y1 + 1, min(y2, height))

    return (x1, y1, x2, y2)


def project_fingerprint_polygon_to_frame(
    detection: Optional[DetectionLike],
    pad_frac: float = 0.01,
    x_start: float = 0.20,
    x_end: float = 0.80,
    y_start: float = 0.05,
    y_end: float = 0.55,
) -> Optional[np.ndarray]:
    """
    Project the fingerprint rectangle from the rectified crop back to the
    original frame coordinate space.

    Returns a float32 array of shape (4, 2) representing the four corners
    of the fingerprint region in frame coordinates, or None if the OBB
    polygon is unavailable/degenerate.

    Corner order: TL, TR, BR, BL (matching the fingerprint box orientation).
    """
    rect = get_obb_rectification(detection, pad_frac=pad_frac)
    if rect is None:
        return None

    # Compute fingerprint box in rectified crop coordinates
    x1, y1, x2, y2 = compute_fingerprint_box(
        width=rect.output_width,
        height=rect.output_height,
        x_start=x_start,
        x_end=x_end,
        y_start=y_start,
        y_end=y_end,
    )

    # Four corners in rectified crop space: TL, TR, BR, BL
    fp_corners_crop = np.float32([
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
    ]).reshape(1, 4, 2)

    # Project back to original frame using inverse homography
    fp_corners_frame = cv2.perspectiveTransform(fp_corners_crop, rect.inverse_matrix)

    return fp_corners_frame[0]  # shape (4, 2)

