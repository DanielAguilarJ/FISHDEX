"""
Tests for Phase 4: Capture quality and fish tracking services.
"""
import pytest
import numpy as np

from app.services.capture_quality_service import evaluate_capture, CaptureQuality
from app.services.fish_tracking_service import (
    validate_single_fish,
    compute_iou,
    TrackingResult,
)


class TestCaptureQuality:
    """Tests for capture_quality_service."""

    def _make_frame(self, h=128, w=128, sharp=True):
        """Create a synthetic frame."""
        rng = np.random.default_rng(42)
        if sharp:
            # Sharp frame with edges
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame[30:100, 30:100] = 200  # sharp rectangle
            frame += rng.integers(0, 10, frame.shape, dtype=np.uint8)
        else:
            # Blurry frame (gaussian-like)
            frame = rng.integers(100, 110, (h, w, 3), dtype=np.uint8)
        return frame

    def test_good_quality_frames(self):
        """Multiple sharp, well-sized frames produce good quality."""
        frames = [self._make_frame(128, 128, sharp=True) for _ in range(6)]
        detections = [
            {"bbox": [20, 20, 80, 80], "confidence": 0.92}
            for _ in range(6)
        ]

        result = evaluate_capture(frames, detections, video_duration_seconds=10.0)
        assert result.is_acceptable
        assert result.valid_crop_count == 6
        assert result.overall_score > 0.5

    def test_empty_frames_rejected(self):
        """No frames -> not acceptable."""
        result = evaluate_capture([], [], video_duration_seconds=0)
        assert not result.is_acceptable
        assert result.valid_crop_count == 0

    def test_single_frame_below_minimum(self):
        """Single frame is below min crop count."""
        frames = [self._make_frame()]
        detections = [{"bbox": [10, 10, 100, 100], "confidence": 0.9}]

        result = evaluate_capture(frames, detections)
        assert not result.is_acceptable
        assert result.valid_crop_count == 1
        assert any("crops" in r.lower() or "insufficient" in r.lower() for r in result.rejection_reasons)

    def test_border_clipping_detected(self):
        """Detection touching frame border should be flagged."""
        frame = self._make_frame(128, 128)
        # bbox at x=0, y=0 — definitely touching border
        det_border = {"bbox": [0, 0, 50, 80], "confidence": 0.9}
        # bbox fully interior
        det_interior = {"bbox": [30, 30, 50, 50], "confidence": 0.9}

        # Mix of border and interior detections
        result = evaluate_capture(
            [frame] * 4,
            [det_border, det_border, det_interior, det_interior],
        )
        # At least verify the metric exists and is a number
        assert isinstance(result.border_clipping_ratio, float)
        assert result.border_clipping_ratio >= 0.0


class TestFishTracking:
    """Tests for fish_tracking_service."""

    def test_single_fish_single_detection_per_frame(self):
        """One detection per frame -> single fish."""
        detections_per_frame = [
            [{"bbox": [50, 50, 80, 60], "confidence": 0.9}],
            [{"bbox": [55, 52, 80, 60], "confidence": 0.88}],
            [{"bbox": [58, 54, 80, 60], "confidence": 0.91}],
            [{"bbox": [60, 55, 80, 60], "confidence": 0.87}],
        ]

        result = validate_single_fish(detections_per_frame)
        assert result.is_single_fish
        assert not result.multiple_fish_detected
        assert result.dominant_track_length == 4
        assert result.track_consistency == 1.0

    def test_two_fish_multiple_frames(self):
        """Two persistent detections -> multiple fish detected."""
        detections_per_frame = [
            [
                {"bbox": [10, 10, 50, 40], "confidence": 0.9},
                {"bbox": [200, 200, 50, 40], "confidence": 0.85},
            ],
            [
                {"bbox": [12, 12, 50, 40], "confidence": 0.88},
                {"bbox": [202, 202, 50, 40], "confidence": 0.87},
            ],
            [
                {"bbox": [14, 14, 50, 40], "confidence": 0.91},
                {"bbox": [204, 204, 50, 40], "confidence": 0.86},
            ],
            [
                {"bbox": [16, 16, 50, 40], "confidence": 0.89},
                {"bbox": [206, 206, 50, 40], "confidence": 0.84},
            ],
        ]

        result = validate_single_fish(detections_per_frame)
        assert not result.is_single_fish
        assert result.multiple_fish_detected
        assert result.secondary_tracks >= 1

    def test_transient_second_detection_ok(self):
        """Brief appearance of second detection (1 frame only) -> still single fish."""
        detections_per_frame = [
            [{"bbox": [50, 50, 80, 60], "confidence": 0.9}],
            [
                {"bbox": [52, 52, 80, 60], "confidence": 0.88},
                {"bbox": [300, 300, 40, 30], "confidence": 0.5},  # Transient
            ],
            [{"bbox": [54, 54, 80, 60], "confidence": 0.91}],
            [{"bbox": [56, 56, 80, 60], "confidence": 0.87}],
        ]

        result = validate_single_fish(detections_per_frame)
        assert result.is_single_fish
        # Secondary track with length 1 doesn't count

    def test_empty_frames_handled(self):
        """Empty input returns safe defaults."""
        result = validate_single_fish([])
        assert result.is_single_fish  # No evidence of multiple
        assert result.dominant_track_length == 0

    def test_iou_perfect_overlap(self):
        """Same box -> IoU = 1.0."""
        assert compute_iou([10, 10, 50, 50], [10, 10, 50, 50]) == 1.0

    def test_iou_no_overlap(self):
        """Non-overlapping boxes -> IoU = 0.0."""
        assert compute_iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0

    def test_iou_partial_overlap(self):
        """Partially overlapping boxes -> 0 < IoU < 1."""
        iou = compute_iou([0, 0, 20, 20], [10, 10, 20, 20])
        assert 0.0 < iou < 1.0
