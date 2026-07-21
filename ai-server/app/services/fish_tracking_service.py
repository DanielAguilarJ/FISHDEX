"""
Fish Tracking Service for FishDex.

Ensures all crops from a video belong to the same individual fish.
Uses simple IoU-based tracking (Hungarian assignment for multi-detection).
"""
from dataclasses import dataclass
from typing import Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrackingResult:
    """Result of fish tracking analysis."""

    dominant_track_id: int
    dominant_track_length: int
    total_detections: int
    secondary_tracks: int  # number of other tracks with 2+ detections
    is_single_fish: bool
    multiple_fish_detected: bool
    track_consistency: float  # 0.0-1.0 how consistent the dominant track is
    rejection_reason: Optional[str] = None


def compute_iou(box_a: list, box_b: list) -> float:
    """Compute Intersection over Union between two boxes in [x, y, w, h] format.

    Args:
        box_a: [x, y, w, h] for box A.
        box_b: [x, y, w, h] for box B.

    Returns:
        IoU value in [0.0, 1.0].
    """
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    # Convert to corner format
    ax1, ay1, ax2, ay2 = ax, ay, ax + aw, ay + ah
    bx1, by1, bx2, by2 = bx, by, bx + bw, by + bh

    # Intersection
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter_area = inter_w * inter_h

    # Union
    area_a = aw * ah
    area_b = bw * bh
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0

    return float(inter_area / union_area)


def _assign_detections_to_tracks(
    prev_detections: list[dict],
    curr_detections: list[dict],
    prev_track_ids: list[int],
    next_track_id: int,
    iou_threshold: float = 0.3,
) -> tuple[list[int], int]:
    """Assign current detections to existing tracks using greedy IoU matching.

    For each detection in the current frame, find the best-matching detection
    in the previous frame by IoU. If IoU > threshold, assign same track ID.
    Otherwise, create a new track.

    Args:
        prev_detections: Detections from previous frame.
        curr_detections: Detections from current frame.
        prev_track_ids: Track IDs assigned to previous frame detections.
        next_track_id: Next available track ID.
        iou_threshold: Minimum IoU to consider same track.

    Returns:
        Tuple of (track_ids for current detections, updated next_track_id).
    """
    if not prev_detections or not curr_detections:
        # All current detections get new track IDs
        new_ids = list(range(next_track_id, next_track_id + len(curr_detections)))
        return new_ids, next_track_id + len(curr_detections)

    n_prev = len(prev_detections)
    n_curr = len(curr_detections)

    # Compute IoU matrix
    iou_matrix = np.zeros((n_curr, n_prev), dtype=np.float64)
    for i, cd in enumerate(curr_detections):
        for j, pd in enumerate(prev_detections):
            iou_matrix[i, j] = compute_iou(cd["bbox"], pd["bbox"])

    # Greedy assignment (Hungarian is overkill for typical fish counts)
    curr_track_ids = [-1] * n_curr
    used_prev = set()

    # Sort by best IoU descending for greedy matching
    pairs = []
    for i in range(n_curr):
        for j in range(n_prev):
            pairs.append((iou_matrix[i, j], i, j))
    pairs.sort(key=lambda x: x[0], reverse=True)

    for iou_val, ci, pi in pairs:
        if iou_val < iou_threshold:
            break
        if curr_track_ids[ci] != -1 or pi in used_prev:
            continue
        curr_track_ids[ci] = prev_track_ids[pi]
        used_prev.add(pi)

    # Assign new track IDs to unmatched detections
    for i in range(n_curr):
        if curr_track_ids[i] == -1:
            curr_track_ids[i] = next_track_id
            next_track_id += 1

    return curr_track_ids, next_track_id


def validate_single_fish(
    detections_per_frame: list[list[dict]],
    iou_threshold: float = 0.3,
    secondary_track_coverage_threshold: float = 0.20,
) -> TrackingResult:
    """Validate that all detections belong to a single fish.

    Args:
        detections_per_frame: List of frames, each containing a list of
            detection dicts with at minimum {"bbox": [x, y, w, h], "confidence": float}.
            Optional key: "angle" (float).
        iou_threshold: Minimum IoU to link detections across frames.
        secondary_track_coverage_threshold: Fraction of total frames a secondary
            track must cover to flag multiple fish.

    Returns:
        TrackingResult with tracking analysis.
    """
    # --- Handle edge cases ---
    if not detections_per_frame:
        logger.warning("validate_single_fish called with empty detections")
        return TrackingResult(
            dominant_track_id=0,
            dominant_track_length=0,
            total_detections=0,
            secondary_tracks=0,
            is_single_fish=True,
            multiple_fish_detected=False,
            track_consistency=0.0,
            rejection_reason="No detections provided",
        )

    # Filter out empty frames for counting but keep indices
    total_frames = len(detections_per_frame)
    total_detections = sum(len(dets) for dets in detections_per_frame)

    if total_detections == 0:
        return TrackingResult(
            dominant_track_id=0,
            dominant_track_length=0,
            total_detections=0,
            secondary_tracks=0,
            is_single_fish=True,
            multiple_fish_detected=False,
            track_consistency=0.0,
            rejection_reason="No detections in any frame",
        )

    # Single detection total — trivially single fish
    if total_detections == 1:
        return TrackingResult(
            dominant_track_id=0,
            dominant_track_length=1,
            total_detections=1,
            secondary_tracks=0,
            is_single_fish=True,
            multiple_fish_detected=False,
            track_consistency=1.0,
        )

    # --- Run IoU tracking ---
    next_track_id = 0
    prev_detections: list[dict] = []
    prev_track_ids: list[int] = []

    # track_id -> list of frame indices where it appears
    track_frames: dict[int, list[int]] = {}

    for frame_idx, frame_dets in enumerate(detections_per_frame):
        if not frame_dets:
            # No detections in this frame; keep prev state
            prev_detections = []
            prev_track_ids = []
            continue

        curr_track_ids, next_track_id = _assign_detections_to_tracks(
            prev_detections, frame_dets, prev_track_ids, next_track_id, iou_threshold
        )

        # Record track appearances
        for tid in curr_track_ids:
            if tid not in track_frames:
                track_frames[tid] = []
            track_frames[tid].append(frame_idx)

        prev_detections = frame_dets
        prev_track_ids = curr_track_ids

    # --- Analyze tracks ---
    if not track_frames:
        return TrackingResult(
            dominant_track_id=0,
            dominant_track_length=0,
            total_detections=total_detections,
            secondary_tracks=0,
            is_single_fish=True,
            multiple_fish_detected=False,
            track_consistency=0.0,
            rejection_reason="Tracking produced no tracks",
        )

    # Find dominant track (longest)
    track_lengths = {tid: len(frames) for tid, frames in track_frames.items()}
    dominant_track_id = max(track_lengths, key=track_lengths.get)  # type: ignore[arg-type]
    dominant_track_length = track_lengths[dominant_track_id]

    # Count secondary tracks (length >= 2)
    secondary_track_ids = [
        tid
        for tid, length in track_lengths.items()
        if tid != dominant_track_id and length >= 2
    ]
    secondary_tracks = len(secondary_track_ids)

    # Check if any secondary track covers significant portion of frames
    multiple_fish_detected = False
    for tid in secondary_track_ids:
        coverage = len(track_frames[tid]) / total_frames
        if coverage >= secondary_track_coverage_threshold:
            multiple_fish_detected = True
            break

    # Track consistency
    track_consistency = (
        dominant_track_length / total_detections if total_detections > 0 else 0.0
    )

    is_single_fish = not multiple_fish_detected

    # Determine rejection reason if applicable
    rejection_reason: Optional[str] = None
    if multiple_fish_detected:
        rejection_reason = (
            f"Multiple fish detected: {secondary_tracks} secondary track(s) "
            f"with significant frame coverage"
        )
    elif not is_single_fish:
        rejection_reason = (
            f"{secondary_tracks} secondary track(s) detected "
            f"(minor, below coverage threshold)"
        )

    return TrackingResult(
        dominant_track_id=dominant_track_id,
        dominant_track_length=dominant_track_length,
        total_detections=total_detections,
        secondary_tracks=secondary_tracks,
        is_single_fish=is_single_fish,
        multiple_fish_detected=multiple_fish_detected,
        track_consistency=float(np.clip(track_consistency, 0.0, 1.0)),
        rejection_reason=rejection_reason,
    )
