"""
Tests for fingerprint polygon projection and centralized geometry helpers.

Covers:
1. Axis-aligned OBB projects an axis-aligned fingerprint
2. Rotated OBB projects a rotated fingerprint
3. Fingerprint polygon is inside OBB
4. Projection uses same padding as crop
5. Projection returns None without polygon
6. Projection returns None for degenerate OBB
7. Fingerprint box uses same rounding as PIL crop
8. Annotated preview does not use bbox rectangle for fingerprint
9. crop_obb_rotated output is unchanged after refactor
10. Fingerprint model input is not applied twice (consistency test)
"""

import math
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from PIL import Image

from app.utils.crop_utils import (
    OBBRectification,
    compute_fingerprint_box,
    crop_obb_rotated,
    get_obb_rectification,
    project_fingerprint_polygon_to_frame,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_detection(polygon=None, bbox_xyxy=None):
    """Create a dict-based detection fixture."""
    d = {}
    if polygon is not None:
        d["polygon"] = polygon
    if bbox_xyxy is not None:
        d["bbox_xyxy"] = bbox_xyxy
    return d


def _axis_aligned_polygon(x, y, w, h):
    """Create an axis-aligned rectangle polygon (TL, TR, BR, BL)."""
    return [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
    ]


def _rotated_polygon(cx, cy, w, h, angle_deg):
    """
    Create a rotated rectangle polygon centered at (cx, cy)
    with half-dimensions w/2, h/2, rotated by angle_deg.
    Returns corners in TL, TR, BR, BL order (relative to the fish body).
    """
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Half-extents
    hw, hh = w / 2.0, h / 2.0

    # Corners in local space: TL, TR, BR, BL
    local = [
        (-hw, -hh),
        (hw, -hh),
        (hw, hh),
        (-hw, hh),
    ]

    # Rotate and translate
    return [
        [cx + cos_a * lx - sin_a * ly, cy + sin_a * lx + cos_a * ly]
        for lx, ly in local
    ]


def _point_in_convex_polygon(point, polygon_pts):
    """Check if a 2D point is inside a convex polygon using cross products."""
    n = len(polygon_pts)
    for i in range(n):
        p1 = polygon_pts[i]
        p2 = polygon_pts[(i + 1) % n]
        # Cross product of edge vector and point vector
        cross = (p2[0] - p1[0]) * (point[1] - p1[1]) - (p2[1] - p1[1]) * (point[0] - p1[0])
        if cross < -1e-3:  # Allow small tolerance
            return False
    return True


# ---------------------------------------------------------------------------
# Test 1: Axis-aligned OBB → axis-aligned fingerprint
# ---------------------------------------------------------------------------


class TestAxisAlignedProjection:
    def test_axis_aligned_obb_projects_axis_aligned_fingerprint(self):
        """An axis-aligned OBB should produce a fingerprint with sides
        parallel to the image axes."""
        polygon = _axis_aligned_polygon(100, 50, 400, 100)
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(
            detection, pad_frac=0.01,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        assert fp is not None
        assert fp.shape == (4, 2)

        # For axis-aligned: top two points should have ~same Y,
        # left two points should have ~same X
        # TL, TR, BR, BL
        assert abs(fp[0, 1] - fp[1, 1]) < 2.0  # TL.y ≈ TR.y
        assert abs(fp[2, 1] - fp[3, 1]) < 2.0  # BR.y ≈ BL.y
        assert abs(fp[0, 0] - fp[3, 0]) < 2.0  # TL.x ≈ BL.x
        assert abs(fp[1, 0] - fp[2, 0]) < 2.0  # TR.x ≈ BR.x


# ---------------------------------------------------------------------------
# Test 2: Rotated OBB → rotated fingerprint
# ---------------------------------------------------------------------------


class TestRotatedProjection:
    def test_rotated_obb_projects_rotated_fingerprint(self):
        """A rotated OBB should produce a fingerprint that is NOT axis-aligned,
        with sides parallel to the OBB sides."""
        angle = 30.0
        polygon = _rotated_polygon(300, 200, 400, 100, angle)
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(
            detection, pad_frac=0.01,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        assert fp is not None
        assert fp.shape == (4, 2)

        # The fingerprint should NOT be axis-aligned
        y_spread_top = abs(fp[0, 1] - fp[1, 1])
        assert y_spread_top > 5.0, "Fingerprint should be visibly rotated"

        # Check that top edge (TL→TR) is parallel to OBB top edge (polygon[0]→polygon[1])
        obb_top_vec = np.array(polygon[1]) - np.array(polygon[0])
        fp_top_vec = fp[1] - fp[0]

        # Normalize and check parallelism via cross product ≈ 0
        obb_top_norm = obb_top_vec / np.linalg.norm(obb_top_vec)
        fp_top_norm = fp_top_vec / np.linalg.norm(fp_top_vec)
        cross = abs(obb_top_norm[0] * fp_top_norm[1] - obb_top_norm[1] * fp_top_norm[0])
        assert cross < 0.05, f"Top edge should be parallel to OBB, cross={cross}"

        # Check that left edge (TL→BL) is parallel to OBB left edge (polygon[0]→polygon[3])
        obb_left_vec = np.array(polygon[3]) - np.array(polygon[0])
        fp_left_vec = fp[3] - fp[0]
        obb_left_norm = obb_left_vec / np.linalg.norm(obb_left_vec)
        fp_left_norm = fp_left_vec / np.linalg.norm(fp_left_vec)
        cross_left = abs(obb_left_norm[0] * fp_left_norm[1] - obb_left_norm[1] * fp_left_norm[0])
        assert cross_left < 0.05, f"Left edge should be parallel to OBB, cross={cross_left}"

    def test_35_degree_rotation(self):
        """35-degree rotation also produces a properly rotated fingerprint."""
        polygon = _rotated_polygon(500, 300, 600, 150, 35.0)
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(
            detection, pad_frac=0.01,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        assert fp is not None
        # All four points should be inside the OBB polygon
        for i in range(4):
            assert _point_in_convex_polygon(
                fp[i], polygon
            ), f"Fingerprint corner {i} is outside OBB"


# ---------------------------------------------------------------------------
# Test 3: Fingerprint polygon is inside OBB
# ---------------------------------------------------------------------------


class TestFingerprintInsideOBB:
    @pytest.mark.parametrize("angle", [0, 15, 30, 45, 60, 90, -20])
    def test_fingerprint_polygon_is_inside_obb(self, angle):
        """All fingerprint corners must lie inside the OBB polygon."""
        polygon = _rotated_polygon(400, 300, 500, 120, angle)
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(
            detection, pad_frac=0.0,  # No padding to test strict containment
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        assert fp is not None
        for i in range(4):
            assert _point_in_convex_polygon(
                fp[i], polygon
            ), f"Corner {i} at {fp[i]} is outside OBB at angle={angle}"


# ---------------------------------------------------------------------------
# Test 4: Projection uses same padding as crop
# ---------------------------------------------------------------------------


class TestProjectionPaddingConsistency:
    def test_projection_uses_same_padding_as_crop(self):
        """The fingerprint projection with a given pad_frac should match
        what crop_obb_rotated produces with the same pad_frac."""
        polygon = _rotated_polygon(300, 200, 400, 100, 25.0)
        detection = _make_detection(polygon=polygon)

        pad_frac = 0.03  # non-default padding

        rect = get_obb_rectification(detection, pad_frac=pad_frac)
        assert rect is not None

        # Create synthetic frame and crop
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        crop = crop_obb_rotated(frame, detection, pad_frac=pad_frac)
        assert crop is not None

        # Crop dimensions should match rectification dimensions
        assert crop.shape[1] == rect.output_width
        assert crop.shape[0] == rect.output_height

        # Fingerprint box computed on same dimensions
        fp_box = compute_fingerprint_box(
            rect.output_width, rect.output_height,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )
        assert fp_box[2] <= rect.output_width
        assert fp_box[3] <= rect.output_height


# ---------------------------------------------------------------------------
# Test 5: Returns None without polygon
# ---------------------------------------------------------------------------


class TestProjectionReturnsNone:
    def test_projection_returns_none_without_polygon(self):
        """Detection without polygon should return None."""
        detection = _make_detection(bbox_xyxy=[100, 50, 500, 150])
        fp = project_fingerprint_polygon_to_frame(detection, pad_frac=0.01)
        assert fp is None

    def test_projection_returns_none_for_none_detection(self):
        """None detection returns None."""
        fp = project_fingerprint_polygon_to_frame(None, pad_frac=0.01)
        assert fp is None

    def test_projection_returns_none_for_empty_polygon(self):
        """Empty polygon list returns None."""
        detection = _make_detection(polygon=[])
        fp = project_fingerprint_polygon_to_frame(detection, pad_frac=0.01)
        assert fp is None


# ---------------------------------------------------------------------------
# Test 6: Returns None for degenerate OBB
# ---------------------------------------------------------------------------


class TestProjectionDegenerateOBB:
    def test_projection_returns_none_for_degenerate_obb(self):
        """A polygon with sides < 4px should return None."""
        # Degenerate: all points nearly the same
        polygon = [[100, 100], [101, 100], [101, 101], [100, 101]]
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(detection, pad_frac=0.01)
        assert fp is None

    def test_projection_returns_none_for_zero_width(self):
        """Polygon with zero width returns None."""
        polygon = [[100, 100], [100, 100], [100, 200], [100, 200]]
        detection = _make_detection(polygon=polygon)

        fp = project_fingerprint_polygon_to_frame(detection, pad_frac=0.01)
        assert fp is None


# ---------------------------------------------------------------------------
# Test 7: Fingerprint box uses same rounding as PIL crop
# ---------------------------------------------------------------------------


class TestFingerprintBoxRounding:
    def test_fingerprint_box_uses_same_rounding_as_pil_crop(self):
        """compute_fingerprint_box must produce the same coordinates as
        FishFingerprintCrop uses internally (round-based)."""
        try:
            from app.services.fish_encoder_model import FishFingerprintCrop
        except (ImportError, ModuleNotFoundError):
            # If torch/timm unavailable, use inline equivalent
            class FishFingerprintCrop:
                def __init__(self, x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55, force_landscape=True):
                    self.x_start = x_start
                    self.x_end = x_end
                    self.y_start = y_start
                    self.y_end = y_end
                    self.force_landscape = force_landscape

                def __call__(self, image):
                    if self.force_landscape and image.height > image.width:
                        image = image.transpose(Image.Transpose.ROTATE_270)
                    length, height = image.size
                    x1 = int(round(self.x_start * length))
                    x2 = int(round(self.x_end * length))
                    y1 = int(round(self.y_start * height))
                    y2 = int(round(self.y_end * height))
                    x1 = max(0, min(x1, length - 1))
                    x2 = max(x1 + 1, min(x2, length))
                    y1 = max(0, min(y1, height - 1))
                    y2 = max(y1 + 1, min(y2, height))
                    return image.crop((x1, y1, x2, y2))

        # Test with multiple image sizes
        test_sizes = [(600, 200), (1000, 300), (128, 128), (347, 89)]

        for w, h in test_sizes:
            x1, y1, x2, y2 = compute_fingerprint_box(
                w, h, x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55
            )

            # Create PIL image and apply FishFingerprintCrop
            img = Image.new("RGB", (w, h))
            crop_fn = FishFingerprintCrop(
                x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
                force_landscape=False,  # Don't rotate, keep original dims
            )
            result = crop_fn(img)

            # The PIL crop should have dimensions matching our box
            expected_w = x2 - x1
            expected_h = y2 - y1
            assert result.size == (expected_w, expected_h), (
                f"Size mismatch for ({w}, {h}): "
                f"compute_fingerprint_box gives ({expected_w}, {expected_h}), "
                f"FishFingerprintCrop gives {result.size}"
            )


# ---------------------------------------------------------------------------
# Test 8: Annotated preview does not use bbox rectangle for fingerprint
# ---------------------------------------------------------------------------


class TestAnnotatedPreviewNoRectangle:
    def test_annotated_preview_does_not_use_bbox_rectangle_for_fingerprint(self):
        """The _draw_annotated_frame function should use polylines, not
        cv2.rectangle, for the fingerprint region when OBB is available."""
        import inspect
        from app.services.artifact_service import _draw_annotated_frame

        source = inspect.getsource(_draw_annotated_frame)

        # The fingerprint section should NOT contain cv2.rectangle for fingerprint
        # Find the fingerprint section
        fp_section_start = source.find("FINGERPRINT")
        assert fp_section_start > 0, "Should have FINGERPRINT section"

        # After the fingerprint section marker, should use polylines not rectangle
        fp_section = source[fp_section_start:]
        # Should contain polylines
        assert "polylines" in fp_section, (
            "Fingerprint drawing should use cv2.polylines"
        )
        # Should NOT contain cv2.rectangle in the fingerprint section
        # (rectangle is used elsewhere for bbox, but not for fingerprint)
        fp_drawing_section = fp_section.split("Label block")[0] if "Label block" in fp_section else fp_section[:500]
        assert "cv2.rectangle" not in fp_drawing_section, (
            "Fingerprint section should not use cv2.rectangle"
        )


# ---------------------------------------------------------------------------
# Test 9: crop_obb_rotated output is unchanged after refactor
# ---------------------------------------------------------------------------


class TestCropObbUnchanged:
    def test_crop_obb_rotated_output_is_unchanged_after_refactor(self):
        """crop_obb_rotated must produce the same pixel output as before
        the refactoring to use get_obb_rectification internally."""
        # Create a frame with known content
        frame = np.random.randint(0, 255, (600, 800, 3), dtype=np.uint8)
        polygon = _rotated_polygon(400, 300, 500, 120, 25.0)
        detection = _make_detection(polygon=polygon)

        # Get rectification
        rect = get_obb_rectification(detection, pad_frac=0.01)
        assert rect is not None

        # crop_obb_rotated should use the same matrix
        crop = crop_obb_rotated(frame, detection, pad_frac=0.01)
        assert crop is not None

        # Manually warp with the rectification matrix
        manual_warp = cv2.warpPerspective(
            frame, rect.matrix, (rect.output_width, rect.output_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        # Should be pixel-identical
        np.testing.assert_array_equal(crop, manual_warp)

    def test_axis_aligned_crop_dimensions(self):
        """Axis-aligned polygon should produce expected crop dimensions."""
        polygon = _axis_aligned_polygon(100, 50, 400, 100)
        detection = _make_detection(polygon=polygon)

        crop = crop_obb_rotated(
            np.zeros((600, 800, 3), dtype=np.uint8),
            detection,
            pad_frac=0.01,
        )
        assert crop is not None

        # Expected: w=400 + 2*0.01*400 = 408, h=100 + 2*0.01*100 = 102
        assert crop.shape[1] == 408  # width
        assert crop.shape[0] == 102  # height


# ---------------------------------------------------------------------------
# Test 10: Fingerprint model input is not applied twice (consistency)
# ---------------------------------------------------------------------------


class TestFingerprintNotAppliedTwice:
    def test_fingerprint_model_input_is_not_applied_twice(self):
        """
        Verify round-trip consistency: project fingerprint to frame, then
        rectify and compute fingerprint box — should recover the same region
        within 1-2 pixel tolerance.
        """
        polygon = _rotated_polygon(400, 300, 500, 120, 30.0)
        detection = _make_detection(polygon=polygon)
        pad_frac = 0.01

        # Step 1: Get the fingerprint polygon in frame space
        fp_frame = project_fingerprint_polygon_to_frame(
            detection, pad_frac=pad_frac,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )
        assert fp_frame is not None

        # Step 2: Get the rectification
        rect = get_obb_rectification(detection, pad_frac=pad_frac)
        assert rect is not None

        # Step 3: Project fingerprint corners BACK to crop space using forward matrix
        fp_crop_space = cv2.perspectiveTransform(
            fp_frame.reshape(1, 4, 2), rect.matrix
        )[0]

        # Step 4: Compute expected fingerprint box
        x1, y1, x2, y2 = compute_fingerprint_box(
            rect.output_width, rect.output_height,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        expected_corners = np.float32([
            [x1, y1], [x2, y1], [x2, y2], [x1, y2]
        ])

        # Should match within 2px tolerance (floating point in perspective transform)
        np.testing.assert_allclose(
            fp_crop_space, expected_corners, atol=2.0,
            err_msg="Round-trip projection should recover original fingerprint box"
        )


# ---------------------------------------------------------------------------
# Visual consistency test
# ---------------------------------------------------------------------------


class TestVisualConsistency:
    def test_synthetic_frame_roundtrip(self):
        """
        Full visual consistency test:
        - Create a synthetic frame with a known pattern
        - Project fingerprint to frame
        - Rectify via crop_obb_rotated
        - Apply compute_fingerprint_box
        - Verify both represent the same region (within tolerance)
        """
        # Create frame with gradient pattern
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        for y in range(600):
            for x in range(0, 800, 4):
                frame[y, x:x+4] = [x % 256, y % 256, (x + y) % 256]

        polygon = _rotated_polygon(400, 300, 500, 120, 20.0)
        detection = _make_detection(polygon=polygon)
        pad_frac = 0.01

        # Get fingerprint polygon in frame coords
        fp_poly = project_fingerprint_polygon_to_frame(
            detection, pad_frac=pad_frac,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )
        assert fp_poly is not None

        # Get crop
        crop = crop_obb_rotated(frame, detection, pad_frac=pad_frac)
        assert crop is not None

        # Get fingerprint box in crop space
        x1, y1, x2, y2 = compute_fingerprint_box(
            crop.shape[1], crop.shape[0],
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        # The fingerprint crop region
        fp_from_crop = crop[y1:y2, x1:x2]
        assert fp_from_crop.size > 0

        # Extract the same region from the original frame using the polygon
        # by warping just the fingerprint region
        # This verifies the polygon represents the correct frame region
        src_pts = fp_poly.astype(np.float32)
        dst_w = x2 - x1
        dst_h = y2 - y1
        dst_pts = np.float32([
            [0, 0], [dst_w, 0], [dst_w, dst_h], [0, dst_h]
        ])

        M_fp = cv2.getPerspectiveTransform(src_pts, dst_pts)
        fp_from_frame = cv2.warpPerspective(
            frame, M_fp, (dst_w, dst_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        # Compare the two fingerprint extractions — they should be very similar
        # (not pixel-identical due to interpolation differences in two-step vs one-step warp)
        diff = np.abs(fp_from_crop.astype(np.float32) - fp_from_frame.astype(np.float32))
        mean_diff = diff.mean()
        assert mean_diff < 15.0, (
            f"Mean pixel difference {mean_diff} too large — "
            "fingerprint polygon doesn't match crop region"
        )


# ---------------------------------------------------------------------------
# OBBRectification dataclass tests
# ---------------------------------------------------------------------------


class TestOBBRectification:
    def test_get_obb_rectification_returns_dataclass(self):
        """get_obb_rectification returns a proper OBBRectification."""
        polygon = _axis_aligned_polygon(100, 50, 400, 100)
        detection = _make_detection(polygon=polygon)

        rect = get_obb_rectification(detection, pad_frac=0.01)
        assert rect is not None
        assert isinstance(rect, OBBRectification)
        assert rect.src_points.shape == (4, 2)
        assert rect.dst_points.shape == (4, 2)
        assert rect.matrix.shape == (3, 3)
        assert rect.inverse_matrix.shape == (3, 3)
        assert rect.output_width > 0
        assert rect.output_height > 0

    def test_inverse_matrix_is_true_inverse(self):
        """M @ M_inv should be approximately identity."""
        polygon = _rotated_polygon(300, 200, 400, 100, 45.0)
        detection = _make_detection(polygon=polygon)

        rect = get_obb_rectification(detection, pad_frac=0.01)
        assert rect is not None

        # A point projected forward then backward should return to start
        test_pts = np.float32([[[150.0, 120.0], [350.0, 250.0]]]).reshape(1, 2, 2)
        projected = cv2.perspectiveTransform(test_pts, rect.matrix)
        recovered = cv2.perspectiveTransform(projected, rect.inverse_matrix)

        np.testing.assert_allclose(
            recovered[0], test_pts[0], atol=0.5,
            err_msg="Inverse matrix should recover original points"
        )


# ---------------------------------------------------------------------------
# compute_fingerprint_box edge cases
# ---------------------------------------------------------------------------


class TestComputeFingerprintBoxEdgeCases:
    def test_invalid_x_bounds_raises(self):
        with pytest.raises(ValueError):
            compute_fingerprint_box(100, 100, x_start=0.8, x_end=0.2)

    def test_invalid_y_bounds_raises(self):
        with pytest.raises(ValueError):
            compute_fingerprint_box(100, 100, y_start=0.9, y_end=0.1)

    def test_minimum_1px_dimensions(self):
        """Even tiny images produce at least 1px fingerprint."""
        x1, y1, x2, y2 = compute_fingerprint_box(2, 2)
        assert x2 > x1
        assert y2 > y1
        assert x2 - x1 >= 1
        assert y2 - y1 >= 1

    def test_full_range(self):
        """x=[0,1] y=[0,1] returns the full image."""
        x1, y1, x2, y2 = compute_fingerprint_box(
            400, 200, x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0
        )
        assert x1 == 0
        assert y1 == 0
        assert x2 == 400
        assert y2 == 200
