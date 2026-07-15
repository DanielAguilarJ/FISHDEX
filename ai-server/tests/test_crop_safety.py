"""
Unit tests for crop safety — strict mode with no fallback.

Tests cover:
  - crop_bbox_aligned_strict returns None for None detection
  - crop_bbox_aligned_strict returns None for degenerate bbox
  - crop_fish_best returns None for degenerate polygon (no center-crop fallback)
  - crop area is < 55% of original frame area for a tight detection

Run from the ai-server directory:
    python -m pytest tests/test_crop_safety.py -v
"""

import sys
import os
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_frame(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _detection(polygon=None, bbox_xyxy=None):
    """Create a minimal detection-like object."""
    class Det:
        pass
    d = Det()
    d.polygon = polygon
    d.bbox_xyxy = bbox_xyxy
    d.confidence = 0.85
    d.class_id = 0
    d.angle = 0.0
    return d


class TestCropBboxAlignedStrict(unittest.TestCase):
    def test_none_detection_returns_none(self):
        from app.utils.crop_utils import crop_bbox_aligned_strict
        result = crop_bbox_aligned_strict(_fake_frame(), None)
        self.assertIsNone(result)

    def test_no_bbox_returns_none(self):
        from app.utils.crop_utils import crop_bbox_aligned_strict
        det = _detection(polygon=None, bbox_xyxy=None)
        result = crop_bbox_aligned_strict(_fake_frame(), det)
        self.assertIsNone(result)

    def test_degenerate_bbox_returns_none(self):
        """bbox with w<=2 or h<=2 → None."""
        from app.utils.crop_utils import crop_bbox_aligned_strict
        det = _detection(bbox_xyxy=(100.0, 100.0, 101.0, 101.0))  # 1x1 px
        result = crop_bbox_aligned_strict(_fake_frame(), det)
        self.assertIsNone(result)

    def test_valid_bbox_returns_crop(self):
        from app.utils.crop_utils import crop_bbox_aligned_strict
        frame = _fake_frame(h=480, w=640)
        det = _detection(bbox_xyxy=(100.0, 100.0, 300.0, 250.0))
        result = crop_bbox_aligned_strict(frame, det)
        self.assertIsNotNone(result)
        self.assertGreater(result.size, 0)


class TestCropFishBest(unittest.TestCase):
    def test_degenerate_polygon_returns_none(self):
        """A polygon with all points at the same location → None (no center-crop!)."""
        from app.utils.crop_utils import crop_fish_best
        det = _detection(
            polygon=[(100.0, 100.0), (100.0, 100.0), (100.0, 100.0), (100.0, 100.0)],
            bbox_xyxy=None,
        )
        result = crop_fish_best(_fake_frame(), det)
        self.assertIsNone(result)

    def test_none_detection_returns_none(self):
        from app.utils.crop_utils import crop_fish_best
        result = crop_fish_best(_fake_frame(), None)
        self.assertIsNone(result)


class TestCropAreaRatio(unittest.TestCase):
    def test_tight_crop_area_below_55_percent(self):
        """A reasonable fish detection should crop < 55% of frame area."""
        from app.utils.crop_utils import crop_bbox_aligned_strict

        frame = _fake_frame(h=480, w=640)
        orig_area = 480 * 640  # 307200

        # Detection covering ~25% of frame: 320x240 region in a 640x480 frame
        det = _detection(bbox_xyxy=(160.0, 120.0, 480.0, 360.0))
        crop = crop_bbox_aligned_strict(frame, det, pad_frac=0.03)

        self.assertIsNotNone(crop)
        crop_area = crop.shape[0] * crop.shape[1]
        ratio = crop_area / orig_area

        self.assertLess(ratio, 0.55,
                        f"Crop covers {ratio:.1%} of frame — should be < 55% for a tight fish crop")

    def test_crop_smaller_than_original(self):
        """Crop shape must differ from original frame shape."""
        from app.utils.crop_utils import crop_bbox_aligned_strict

        frame = _fake_frame(h=480, w=640)
        det = _detection(bbox_xyxy=(100.0, 100.0, 300.0, 250.0))
        crop = crop_bbox_aligned_strict(frame, det, pad_frac=0.03)

        self.assertIsNotNone(crop)
        is_same = (crop.shape[0] == frame.shape[0] and crop.shape[1] == frame.shape[1])
        self.assertFalse(is_same, "Crop must be smaller than the full frame")

    def test_pad_horizontal_crop_to_vertical_aspect(self):
        from app.utils.crop_utils import pad_image_to_aspect
        crop = np.zeros((100, 400, 3), dtype=np.uint8)    # horizontal fish crop
        padded = pad_image_to_aspect(crop, target_aspect=500 / 1000)
        self.assertIsNotNone(padded)
        h, w = padded.shape[:2]
        self.assertLess(abs((w / h) - 0.5), 0.02)
        self.assertGreater(h, w)

    def test_preserve_landscape_frame_aspect(self):
        from app.utils.crop_utils import pad_image_to_aspect
        crop = np.zeros((100, 400, 3), dtype=np.uint8)
        padded = pad_image_to_aspect(crop, target_aspect=1000 / 500)
        self.assertIsNotNone(padded)
        h, w = padded.shape[:2]
        self.assertLess(abs((w / h) - 2.0), 0.02)
        self.assertGreater(w, h)


if __name__ == "__main__":
    unittest.main()
