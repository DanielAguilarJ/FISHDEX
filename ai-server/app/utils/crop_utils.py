"""
FishDex AI Server — OBB Crop Utilities
=======================================
Two crop strategies for fish detections from YOLOv8 OBB models:

  crop_obb_rotated(frame, detection, pad_frac=0.08)
    Perspective-warps the exact OBB polygon region to a tight rectangle.
    Uses the 4 polygon corners from the detector (already in TL→TR→BR→BL
    order from detector_service._obb_to_corners).  No rotation matrix
    angle arithmetic — cv2.getPerspectiveTransform maps the parallelogram
    directly to a rectangle, so the fish is always deskewed regardless of
    which direction it is tilted.
    Long side → output width (fish body horizontal).

  crop_bbox_aligned(frame, detection, pad_frac=0.08)
    Standard axis-aligned bounding-box crop.
    Uses bbox_xyxy from the detection, adds padding, clips to frame.

  crop_fish_best(frame, detection)
    Primary selector: tries OBB perspective warp first, falls back to
    axis-aligned bbox crop.
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
    pad_frac: float = 0.08,
) -> Optional[np.ndarray]:
    """
    Perspective-warp the OBB polygon to a tight rectangular crop.

    The 4 polygon corners from detector_service are ordered:
      polygon[0] = TL (top-left in unrotated space)
      polygon[1] = TR (top-right)
      polygon[2] = BR (bottom-right)
      polygon[3] = BL (bottom-left)

    Side lengths:
      polygon[0]→polygon[1] = OBB "width"  (w)
      polygon[1]→polygon[2] = OBB "height" (h)

    To make the fish horizontal in the output, we ensure the long
    side maps to the output width. If h > w we rotate the corner
    assignment by one position so h becomes the width.

    Returns a BGR ndarray of exactly the OBB region + pad_frac,
    or None if the polygon is unavailable / degenerate.
    """
    polygon = _get_polygon(detection)
    if polygon is None or len(polygon) < 4:
        return None

    # Build corner vectors from the polygon
    p = [np.array([float(v[0]), float(v[1])], dtype=np.float64) for v in polygon[:4]]

    # Measure both side lengths of the OBB
    w_side = float(np.linalg.norm(p[1] - p[0]))   # TL → TR
    h_side = float(np.linalg.norm(p[2] - p[1]))   # TR → BR

    if w_side < 2.0 or h_side < 2.0:
        return None  # degenerate box

    # Choose which side is "width" (long) and orient the corners accordingly
    if w_side >= h_side:
        # Already landscape: p[0]=TL, p[1]=TR, p[2]=BR, p[3]=BL
        src_pts = np.float32([p[0], p[1], p[2], p[3]])
        w_out, h_out = w_side, h_side
    else:
        # Portrait → rotate 90° so h becomes the width
        # New TL=p[3], TR=p[0], BR=p[1], BL=p[2]
        src_pts = np.float32([p[3], p[0], p[1], p[2]])
        w_out, h_out = h_side, w_side

    # Output canvas dimensions + symmetrical padding
    pw = w_out * pad_frac
    ph = h_out * pad_frac
    out_w = max(4, int(round(w_out + 2.0 * pw)))
    out_h = max(4, int(round(h_out + 2.0 * ph)))

    dst_pts = np.float32([
        [pw,            ph           ],   # TL
        [out_w - pw,    ph           ],   # TR
        [out_w - pw,    out_h - ph   ],   # BR
        [pw,            out_h - ph   ],   # BL
    ])

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        frame, M, (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    if warped is None or warped.size == 0:
        return None

    logger.debug(
        "OBB crop: %.0fx%.0f OBB → %dx%d output (pad=%.0f%%)",
        w_out, h_out, out_w, out_h, pad_frac * 100,
    )
    return warped


def crop_bbox_aligned(
    frame: np.ndarray,
    detection,
    pad_frac: float = 0.08,
) -> np.ndarray:
    """
    Axis-aligned bounding-box crop with optional padding.

    Uses bbox_xyxy from the detection. Falls back to a 70 % center crop
    if no detection is available.
    """
    h_img, w_img = frame.shape[:2]
    bbox = _get_bbox(detection)
    if bbox and len(bbox) >= 4:
        x1_f, y1_f, x2_f, y2_f = (
            float(bbox[0]), float(bbox[1]),
            float(bbox[2]), float(bbox[3]),
        )
        bw = x2_f - x1_f
        bh = y2_f - y1_f
        if bw > 1.0 and bh > 1.0:
            x1 = max(0, int(x1_f - bw * pad_frac))
            y1 = max(0, int(y1_f - bh * pad_frac))
            x2 = min(w_img, int(x2_f + bw * pad_frac))
            y2 = min(h_img, int(y2_f + bh * pad_frac))
            if x2 > x1 and y2 > y1:
                return frame[y1:y2, x1:x2]

    # Fallback: center 70 %
    cx, cy = w_img // 2, h_img // 2
    cw = int(w_img * 0.70) // 2
    ch = int(h_img * 0.70) // 2
    return frame[
        max(0, cy - ch): min(h_img, cy + ch),
        max(0, cx - cw): min(w_img, cx + cw),
    ]


def crop_fish_best(frame: np.ndarray, detection) -> np.ndarray:
    """
    Primary crop selector.

    Tries OBB perspective warp first (exact OBB region, fish horizontal).
    Falls back to axis-aligned bbox crop if polygon is unavailable.
    """
    obb = crop_obb_rotated(frame, detection)
    if obb is not None and obb.size > 0:
        return obb
    return crop_bbox_aligned(frame, detection)
