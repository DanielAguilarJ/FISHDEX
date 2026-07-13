"""
Unit tests for the YOLOv8 OBB detector parser.

Tests cover:
  - Correct column layout for nc=1 (xywh_conf_angle — Ultralytics default)
  - Alternate layout (xywh_angle_conf)
  - NMS removes duplicate overlapping predictions
  - Letterbox coordinate recovery for non-square frames
  - Out-of-range confidence is rejected
  - Empty output when all predictions below threshold

Run from the ai-server directory:
    python -m pytest tests/test_detector.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Helper: build a synthetic ONNX output tensor shaped [1, n_cols, N].
#
# Real ONNX output from YOLOv8 OBB is [1, n_cols, 8400].
# The parser checks: if dim0 < dim1 → transpose to (N, n_cols).
# So we need N > n_cols for the auto-transpose to fire correctly.
#
# Strategy: pad with dummy below-threshold rows so N is always > n_cols.
# The conf_threshold is 0.30, so padding with conf=0.0 is safe.
# ---------------------------------------------------------------------------
_ZERO_ROW_6 = (0.0, 0.0, 10.0, 10.0, 0.0, 0.0)  # below-threshold 6-col row


def _make_output(rows: list, pad_to: int = 20) -> np.ndarray:
    """
    rows: list of tuples, each representing one VALID prediction.
    pad_to: minimum number of rows (pads with zero/below-threshold rows).
    Returns ndarray of shape [1, n_cols, N] matching real ONNX output.
    """
    n_cols = len(rows[0])
    zero_row = tuple([0.0] * n_cols)

    padded = list(rows)
    while len(padded) < pad_to:
        padded.append(zero_row)

    arr = np.array(padded, dtype=np.float32)   # (N, n_cols)
    arr = arr.T                                 # (n_cols, N)
    arr = arr[np.newaxis, ...]                  # (1, n_cols, N)
    return arr


def _make_service(layout: str = "xywh_conf_angle"):
    """Create a DetectorService with a mocked ONNX session and patched settings."""
    from app.services import detector_service as ds_mod

    mock_settings = MagicMock()
    mock_settings.detector_output_layout = layout
    mock_settings.detector_nms_iou_threshold = 0.45
    mock_settings.detector_confidence_threshold = 0.30

    patcher = patch.object(ds_mod, "settings", mock_settings)
    patcher.start()

    svc = ds_mod.DetectorService.__new__(ds_mod.DetectorService)
    svc.confidence_threshold = 0.30
    svc._available = True
    svc.session = MagicMock()
    svc.model_path = MagicMock()

    return svc, patcher


# ---------------------------------------------------------------------------
# Test 1: xywh_conf_angle (Ultralytics default for nc=1)
# ---------------------------------------------------------------------------

class TestColumnLayoutConfAngle(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service("xywh_conf_angle")

    def tearDown(self):
        self.patcher.stop()

    def test_reads_conf_from_col4(self):
        """pred[4] must be confidence (0.85), pred[5] must be angle (0.1)."""
        raw = _make_output([(320.0, 320.0, 100.0, 50.0, 0.85, 0.1)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 1, "Expected exactly one detection")
        self.assertAlmostEqual(dets[0].confidence, 0.85, places=4)
        self.assertAlmostEqual(dets[0].angle, 0.1, places=4)

    def test_rejects_swapped_angle_as_conf(self):
        """When angle (1.5 rad) lands in col4, conf > 1.0 → must be rejected."""
        raw = _make_output([(320.0, 320.0, 100.0, 50.0, 1.5, 0.85)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 0, "Swapped conf > 1.0 must be rejected")


# ---------------------------------------------------------------------------
# Test 2: xywh_angle_conf (alternate layout)
# ---------------------------------------------------------------------------

class TestColumnLayoutAngleConf(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service("xywh_angle_conf")

    def tearDown(self):
        self.patcher.stop()

    def test_reads_conf_from_col5(self):
        """pred[5] must be confidence (0.75), pred[4] must be angle (0.3)."""
        raw = _make_output([(320.0, 320.0, 80.0, 40.0, 0.3, 0.75)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 1)
        self.assertAlmostEqual(dets[0].confidence, 0.75, places=4)
        self.assertAlmostEqual(dets[0].angle, 0.3, places=4)


# ---------------------------------------------------------------------------
# Test 3: NMS removes duplicate overlapping predictions
# ---------------------------------------------------------------------------

class TestNMS(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service()

    def tearDown(self):
        self.patcher.stop()

    def test_nms_removes_duplicates(self):
        """Two nearly identical boxes → only one survives NMS."""
        raw = _make_output([
            (320.0, 320.0, 100.0, 60.0, 0.90, 0.05),
            (322.0, 321.0, 100.0, 60.0, 0.85, 0.05),
        ])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 1, "NMS must suppress the near-duplicate")
        self.assertAlmostEqual(dets[0].confidence, 0.90, places=4)

    def test_nms_keeps_non_overlapping(self):
        """Two boxes far apart → both survive NMS."""
        raw = _make_output([
            (100.0, 100.0, 60.0, 40.0, 0.80, 0.1),
            (500.0, 500.0, 60.0, 40.0, 0.75, 0.1),
        ])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 2, "Non-overlapping boxes must both survive NMS")


# ---------------------------------------------------------------------------
# Test 4: Letterbox coordinate recovery for non-square frames
# ---------------------------------------------------------------------------

class TestLetterboxCoordRecovery(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service()

    def tearDown(self):
        self.patcher.stop()

    def test_coords_within_original_bounds_wide_frame(self):
        """Detections on a 1280×720 letterboxed frame must stay within original bounds."""
        orig_w, orig_h = 1280, 720
        ratio = min(640 / orig_w, 640 / orig_h)      # 0.5
        new_w = int(round(orig_w * ratio))             # 640
        new_h = int(round(orig_h * ratio))             # 360
        pad_left = (640 - new_w) // 2                 # 0
        pad_top  = (640 - new_h) // 2                 # 140

        raw = _make_output([(320.0, 320.0, 100.0, 60.0, 0.85, 0.05)])
        dets = self.svc._parse_obb_output(
            raw, ratio=ratio, pad_left=pad_left, pad_top=pad_top,
            orig_h=orig_h, orig_w=orig_w, conf_threshold=0.30,
        )

        self.assertEqual(len(dets), 1)
        x1, y1, x2, y2 = dets[0].bbox_xyxy
        self.assertGreaterEqual(x1, 0.0)
        self.assertGreaterEqual(y1, 0.0)
        self.assertLessEqual(x2, float(orig_w))
        self.assertLessEqual(y2, float(orig_h))


# ---------------------------------------------------------------------------
# Test 5: Confidence and box guards
# ---------------------------------------------------------------------------

class TestConfGuard(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service()

    def tearDown(self):
        self.patcher.stop()

    def test_conf_above_one_rejected(self):
        """conf > 1.0 (e.g. angle value in conf column) → rejected."""
        raw = _make_output([(320.0, 320.0, 80.0, 50.0, 2.3, 0.1)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 0)

    def test_conf_nan_rejected(self):
        """NaN confidence → rejected."""
        raw = _make_output([(320.0, 320.0, 80.0, 50.0, float("nan"), 0.1)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 0)

    def test_degenerate_box_rejected(self):
        """Box with w=1 and h=1 in letterbox space → rejected."""
        raw = _make_output([(320.0, 320.0, 1.0, 1.0, 0.95, 0.1)])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 0)


# ---------------------------------------------------------------------------
# Test 6: All predictions below threshold → empty list
# ---------------------------------------------------------------------------

class TestNegativeThreshold(unittest.TestCase):
    def setUp(self):
        self.svc, self.patcher = _make_service()

    def tearDown(self):
        self.patcher.stop()

    def test_no_detections_below_threshold(self):
        raw = _make_output([
            (200.0, 200.0, 80.0, 50.0, 0.10, 0.2),
            (300.0, 300.0, 70.0, 40.0, 0.05, 0.1),
        ])
        dets = self.svc._parse_obb_output(raw, ratio=1.0, pad_left=0, pad_top=0,
                                           orig_h=640, orig_w=640, conf_threshold=0.30)
        self.assertEqual(len(dets), 0)


if __name__ == "__main__":
    unittest.main()
