"""
FishDex AI Server — OBB Crop Utilities
=======================================
Tight fish crops using the OBB polygon from YOLOv8 detection.
NO fallback to center-crop — if there's no valid detection, returns None.

  crop_obb_rotated(frame, detection, pad_frac=0.03)
    Perspective-warps the exact OBB polygon to a tight rectangle.
    Fish body axis → horizontal.  Returns None if polygon unavailable.

  crop_bbox_aligned_strict(frame, detection, pad_frac=0.03)
    Axis-aligned bbox crop. Returns None if no bbox (NO fallback 70%).

  crop_fish_best(frame, detection, pad_frac=0.03)
    Tries OBB first, then bbox_strict. Returns None if neither works.
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _get_polygon(detection) -> Optional[list]:
    """Extract the OBB polygon corner list from any detection object."""
    if detection is None:
        return None
    if isinstance(detection, dict):
        return detection.get("polygon")
    return getattr(detection, "polygon", None)


def _get_bbox(detection) -> Optional[tuple]:
    """Extract the axis-aligned bbox_xyxy from any detection object."""
    if detection is None:
        return None
    if isinstance(detection, dict):
        return detection.get("bbox_xyxy") or detection.get("bbox")
    return getattr(detection, "bbox_xyxy", None)


def crop_obb_rotated(
    frame: np.ndarray,
    detection,
    pad_frac: float = 0.03,
) -> Optional[np.ndarray]:
    """
    Perspective-warp the OBB polygon to a tight rectangular crop.

    Uses the 4 polygon corners directly with cv2.getPerspectiveTransform.
    The long side of the OBB maps to the output width (fish horizontal).
    pad_frac = 3% padding on each side.

    Returns None if polygon is unavailable or degenerate.
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

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        frame, M, (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    if warped is None or warped.size == 0:
        return None

    return warped


def crop_bbox_aligned_strict(
    frame: np.ndarray,
    detection,
    pad_frac: float = 0.03,
) -> Optional[np.ndarray]:
    """
    Axis-aligned bounding-box crop with 3% padding.
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
    detection,
    pad_frac: float = 0.03,
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
