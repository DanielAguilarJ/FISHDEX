"""
FishDex AI Server — OBB Crop Utilities
=======================================
Two crop strategies for fish detections from YOLOv8 OBB models:

  crop_obb_rotated(frame, detection, pad_frac=0.10)
    Deskews the frame so the fish lies axis-aligned, then crops it.
    Uses cv2.minAreaRect on the OBB polygon corners, rotates the image
    around the fish center, then extracts the straightened rectangle.
    → Best for ML embeddings, display, and training with fish aligned.

  crop_bbox_aligned(frame, detection, pad_frac=0.08)
    Standard axis-aligned bounding-box crop (no rotation).
    → Simpler crop, good for diversity in training datasets.

  crop_fish_best(frame, detection)
    Tries OBB-rotated first, falls back to axis-aligned.
    → Use this as the primary crop in the pipeline.
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
    pad_frac: float = 0.10,
) -> Optional[np.ndarray]:
    """
    Crop the fish region by rotating the frame to align with the OBB.

    Algorithm:
      1. Feed the OBB polygon corners into cv2.minAreaRect to get a clean
         (center, (w_rect, h_rect), angle_deg) representation.
      2. Ensure width >= height so the fish body axis is horizontal in the output.
      3. Expand the canvas with BORDER_REPLICATE padding to prevent edge clipping.
      4. Rotate the padded frame by angle_deg around the fish center so the OBB
         becomes axis-aligned.
      5. Extract [cy ± h_rect/2, cx ± w_rect/2] + pad_frac from the rotated frame.

    Returns:
        BGR ndarray of the deskewed fish crop, or None if polygon is unavailable.
    """
    polygon = _get_polygon(detection)
    if polygon is None or len(polygon) < 4:
        return None

    h_img, w_img = frame.shape[:2]
    pts = np.array(
        [[float(p[0]), float(p[1])] for p in polygon], dtype=np.float32
    )

    rect = cv2.minAreaRect(pts)
    center, (w_rect, h_rect), angle_deg = rect

    if w_rect < 4.0 or h_rect < 4.0:
        return None  # degenerate / empty box

    # ── Ensure the long side is the "width" (fish body axis = horizontal) ──
    if w_rect < h_rect:
        w_rect, h_rect = h_rect, w_rect
        angle_deg += 90.0

    # ── Expand canvas so the fish is never clipped near image borders ──────
    border = int(max(w_rect, h_rect) * 0.30) + 20
    padded = cv2.copyMakeBorder(
        frame, border, border, border, border, cv2.BORDER_REPLICATE
    )
    # Shift OBB center to padded-frame coordinate space
    pcx = float(center[0]) + border
    pcy = float(center[1]) + border

    # ── Rotate the padded frame around the fish center ──────────────────────
    M = cv2.getRotationMatrix2D((pcx, pcy), angle_deg, 1.0)
    rotated = cv2.warpAffine(
        padded, M,
        (padded.shape[1], padded.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    # ── Crop the now axis-aligned fish rectangle (+ padding fraction) ───────
    half_w = w_rect / 2.0 * (1.0 + pad_frac)
    half_h = h_rect / 2.0 * (1.0 + pad_frac)
    x1 = max(0, int(pcx - half_w))
    y1 = max(0, int(pcy - half_h))
    x2 = min(rotated.shape[1], int(pcx + half_w))
    y2 = min(rotated.shape[0], int(pcy + half_h))

    if x2 > x1 and y2 > y1:
        return rotated[y1:y2, x1:x2]
    return None


def crop_bbox_aligned(
    frame: np.ndarray,
    detection,
    pad_frac: float = 0.08,
) -> np.ndarray:
    """
    Axis-aligned bounding-box crop with optional padding.

    Uses the bbox_xyxy (min axis-aligned rect) from the detection.
    Falls back to a 70 % center crop if no detection is available.
    """
    h_img, w_img = frame.shape[:2]
    bbox = _get_bbox(detection)
    if bbox and len(bbox) >= 4:
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        if bw > 0 and bh > 0:
            x1 = max(0, int(bbox[0] - bw * pad_frac))
            y1 = max(0, int(bbox[1] - bh * pad_frac))
            x2 = min(w_img, int(bbox[2] + bw * pad_frac))
            y2 = min(h_img, int(bbox[3] + bh * pad_frac))
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

    Tries OBB-rotated first (aligned with fish body axis).
    Falls back to axis-aligned bbox crop if polygon is unavailable.
    """
    obb = crop_obb_rotated(frame, detection)
    if obb is not None and obb.size > 0:
        return obb
    return crop_bbox_aligned(frame, detection)
