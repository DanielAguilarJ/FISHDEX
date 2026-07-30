"""
Unit tests for the image-processing primitives.

Covers the geometry helpers in ``app.utils.crop_utils``, frame selection in
``app.utils.video``, upload media validation, and the behaviour of the OBB ROI
service when the detector finds no fish.

These functions sit directly on the identification hot path: a silent regression
here degrades matching accuracy without raising anything, so the invariants are
asserted explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.utils.crop_utils import (
    compute_fingerprint_box,
    crop_bbox_aligned_strict,
    crop_fish_best,
    crop_obb_rotated,
    get_obb_rectification,
    pad_image_to_aspect,
)
from app.utils.media_validation import (
    MediaValidationError,
    looks_like_supported_media,
    resolve_media_type,
    safe_suffix_for,
)
from app.utils.video import select_best_frame, select_best_n_frames


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────
def make_frame(width: int = 640, height: int = 480, value: int = 120) -> np.ndarray:
    """Build a uniform BGR frame."""
    return np.full((height, width, 3), value, dtype=np.uint8)


def make_detection(
    polygon: list[tuple[float, float]] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    confidence: float = 0.9,
) -> dict:
    """Build a detection dict in the shape the crop helpers accept."""
    detection: dict = {"confidence": confidence}
    if polygon is not None:
        detection["polygon"] = polygon
    if bbox is not None:
        detection["bbox_xyxy"] = bbox
    return detection


AXIS_ALIGNED_POLYGON = [(100.0, 200.0), (300.0, 200.0), (300.0, 260.0), (100.0, 260.0)]


# ─────────────────────────────────────────────────────────────────────────────
# get_obb_rectification
# ─────────────────────────────────────────────────────────────────────────────
def test_rectification_puts_the_long_side_on_the_width() -> None:
    """A fish is always rectified to a horizontal rectangle."""
    rectification = get_obb_rectification(
        make_detection(polygon=AXIS_ALIGNED_POLYGON), pad_frac=0.0
    )

    assert rectification is not None
    assert rectification.output_width > rectification.output_height
    assert rectification.output_width == pytest.approx(200, abs=1)
    assert rectification.output_height == pytest.approx(60, abs=1)


def test_rectification_rotates_corners_for_a_vertical_fish() -> None:
    """When the fish is taller than wide, the short side becomes the height."""
    vertical_polygon = [(100.0, 100.0), (160.0, 100.0), (160.0, 400.0), (100.0, 400.0)]

    rectification = get_obb_rectification(
        make_detection(polygon=vertical_polygon), pad_frac=0.0
    )

    assert rectification is not None
    assert rectification.output_width == pytest.approx(300, abs=1)
    assert rectification.output_height == pytest.approx(60, abs=1)


def test_rectification_matrices_are_mutual_inverses() -> None:
    """
    The inverse homography must undo the forward one.

    The fingerprint polygon is projected back into frame coordinates using the
    inverse matrix, so a mismatch would draw the overlay in the wrong place.
    """
    rectification = get_obb_rectification(
        make_detection(polygon=AXIS_ALIGNED_POLYGON), pad_frac=0.02
    )
    assert rectification is not None

    product = rectification.matrix @ rectification.inverse_matrix
    np.testing.assert_allclose(product / product[2, 2], np.eye(3), atol=1e-6)


def test_rectification_returns_none_without_a_polygon() -> None:
    assert get_obb_rectification(make_detection(bbox=(0, 0, 10, 10))) is None


def test_rectification_returns_none_for_a_degenerate_polygon() -> None:
    """Sub-4px sides cannot produce a usable crop."""
    degenerate = [(10.0, 10.0), (12.0, 10.0), (12.0, 12.0), (10.0, 12.0)]
    assert get_obb_rectification(make_detection(polygon=degenerate)) is None


def test_rectification_returns_none_for_none_detection() -> None:
    assert get_obb_rectification(None) is None


def test_rectification_padding_grows_the_output() -> None:
    unpadded = get_obb_rectification(
        make_detection(polygon=AXIS_ALIGNED_POLYGON), pad_frac=0.0
    )
    padded = get_obb_rectification(
        make_detection(polygon=AXIS_ALIGNED_POLYGON), pad_frac=0.10
    )

    assert unpadded is not None and padded is not None
    assert padded.output_width > unpadded.output_width
    assert padded.output_height > unpadded.output_height


# ─────────────────────────────────────────────────────────────────────────────
# crop_obb_rotated / crop_bbox_aligned_strict / crop_fish_best
# ─────────────────────────────────────────────────────────────────────────────
def test_crop_obb_rotated_returns_a_horizontal_crop() -> None:
    frame = make_frame()
    crop = crop_obb_rotated(frame, make_detection(polygon=AXIS_ALIGNED_POLYGON))

    assert crop is not None
    height, width = crop.shape[:2]
    assert width > height


def test_crop_obb_rotated_returns_none_without_polygon() -> None:
    frame = make_frame()
    assert crop_obb_rotated(frame, make_detection(bbox=(0, 0, 100, 100))) is None


def test_crop_bbox_aligned_strict_respects_frame_bounds() -> None:
    """A bbox extending past the frame edge must be clamped, not wrapped."""
    frame = make_frame(width=200, height=100)
    crop = crop_bbox_aligned_strict(
        frame, make_detection(bbox=(150.0, 50.0, 400.0, 300.0)), pad_frac=0.0
    )

    assert crop is not None
    height, width = crop.shape[:2]
    assert width <= 200
    assert height <= 100
    assert width > 0 and height > 0


def test_crop_bbox_aligned_strict_returns_none_for_inverted_bbox() -> None:
    frame = make_frame()
    assert (
        crop_bbox_aligned_strict(frame, make_detection(bbox=(300.0, 300.0, 100.0, 100.0)))
        is None
    )


def test_crop_fish_best_prefers_the_oriented_polygon() -> None:
    """
    With both a polygon and a bbox available, the deskewed OBB crop wins because
    it is what the ReID encoder was trained on.
    """
    frame = make_frame()
    detection = make_detection(
        polygon=AXIS_ALIGNED_POLYGON, bbox=(0.0, 0.0, 640.0, 480.0)
    )

    crop = crop_fish_best(frame, detection)
    obb_crop = crop_obb_rotated(frame, detection)

    assert crop is not None and obb_crop is not None
    assert crop.shape == obb_crop.shape


def test_crop_fish_best_falls_back_to_bbox_without_polygon() -> None:
    frame = make_frame()
    crop = crop_fish_best(frame, make_detection(bbox=(10.0, 10.0, 210.0, 110.0)))

    assert crop is not None
    assert crop.size > 0


def test_crop_fish_best_returns_none_for_no_detection() -> None:
    """The no-detection path must return None rather than raise."""
    assert crop_fish_best(make_frame(), None) is None


# ─────────────────────────────────────────────────────────────────────────────
# pad_image_to_aspect
# ─────────────────────────────────────────────────────────────────────────────
def test_pad_image_to_aspect_reaches_the_target_ratio() -> None:
    image = make_frame(width=200, height=100)
    padded = pad_image_to_aspect(image, target_aspect=1.0)

    assert padded is not None
    height, width = padded.shape[:2]
    assert width / height == pytest.approx(1.0, abs=0.02)


def test_pad_image_to_aspect_never_scales_the_original_content() -> None:
    """Padding must add border pixels, never resample the image."""
    image = make_frame(width=200, height=100)
    padded = pad_image_to_aspect(image, target_aspect=0.5)

    assert padded is not None
    height, width = padded.shape[:2]
    assert width >= 200 and height >= 100


def test_pad_image_to_aspect_is_a_noop_when_already_correct() -> None:
    image = make_frame(width=200, height=100)
    padded = pad_image_to_aspect(image, target_aspect=2.0)

    assert padded is not None
    assert padded.shape == image.shape


def test_pad_image_to_aspect_handles_empty_input() -> None:
    assert pad_image_to_aspect(np.zeros((0, 0, 3), dtype=np.uint8), 1.0) is None
    assert pad_image_to_aspect(None, 1.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# compute_fingerprint_box
# ─────────────────────────────────────────────────────────────────────────────
def test_fingerprint_box_matches_the_requested_fractions() -> None:
    x1, y1, x2, y2 = compute_fingerprint_box(
        width=1000, height=200, x_start=0.2, x_end=0.8, y_start=0.05, y_end=0.55
    )

    assert (x1, x2) == (200, 800)
    assert (y1, y2) == (10, 110)


def test_fingerprint_box_always_has_positive_area() -> None:
    """Rounding on a tiny crop must not collapse the box."""
    x1, y1, x2, y2 = compute_fingerprint_box(
        width=3, height=3, x_start=0.49, x_end=0.51, y_start=0.49, y_end=0.51
    )

    assert x2 > x1
    assert y2 > y1


def test_fingerprint_box_stays_inside_the_crop() -> None:
    x1, y1, x2, y2 = compute_fingerprint_box(
        width=64, height=32, x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0
    )

    assert 0 <= x1 < x2 <= 64
    assert 0 <= y1 < y2 <= 32


@pytest.mark.parametrize(
    ("x_start", "x_end", "y_start", "y_end"),
    [
        (0.8, 0.2, 0.0, 1.0),  # x inverted
        (0.0, 1.0, 0.9, 0.1),  # y inverted
        (-0.1, 0.5, 0.0, 1.0),  # x below range
        (0.0, 1.5, 0.0, 1.0),  # x above range
        (0.5, 0.5, 0.0, 1.0),  # zero width
    ],
)
def test_fingerprint_box_rejects_invalid_bounds(
    x_start: float, x_end: float, y_start: float, y_end: float
) -> None:
    with pytest.raises(ValueError):
        compute_fingerprint_box(
            width=100,
            height=100,
            x_start=x_start,
            x_end=x_end,
            y_start=y_start,
            y_end=y_end,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Frame selection
# ─────────────────────────────────────────────────────────────────────────────
def test_select_best_frame_prefers_the_sharpest_frame() -> None:
    """
    Sharpness is measured with a Laplacian variance, so a high-contrast frame
    must beat a flat one.
    """
    import cv2

    flat = make_frame(value=128)
    sharp = make_frame(value=0)
    cv2.rectangle(sharp, (100, 100), (300, 300), (255, 255, 255), -1)
    cv2.rectangle(sharp, (150, 150), (250, 250), (0, 0, 0), -1)

    best = select_best_frame([flat, sharp])

    assert np.array_equal(best, sharp)


def test_select_best_n_frames_returns_at_most_n() -> None:
    frames = [make_frame(value=v) for v in range(10, 100, 10)]
    assert len(select_best_n_frames(frames, n=3)) == 3


def test_select_best_n_frames_handles_fewer_frames_than_requested() -> None:
    frames = [make_frame(value=10), make_frame(value=20)]
    assert len(select_best_n_frames(frames, n=5)) == 2


def test_select_best_n_frames_on_a_single_frame() -> None:
    frames = [make_frame()]
    assert len(select_best_n_frames(frames, n=5)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Upload media validation
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("content_type", "filename", "expected"),
    [
        ("image/jpeg", "photo.jpg", "image"),
        ("image/png", "photo.png", "image"),
        ("video/mp4", "clip.mp4", "video"),
        ("video/quicktime", "clip.mov", "video"),
        ("", "clip.mkv", "video"),
        ("", "photo.HEIC", "image"),
        ("application/octet-stream", "recording", "video"),
    ],
)
def test_resolve_media_type(content_type: str, filename: str, expected: str) -> None:
    assert resolve_media_type(content_type, filename) == expected


def test_resolve_media_type_rejects_unsupported_types() -> None:
    with pytest.raises(MediaValidationError):
        resolve_media_type("application/pdf", "document.pdf")


def test_safe_suffix_rejects_a_hostile_extension() -> None:
    """
    A client-supplied .html must never reach disk: the storage directory is
    served statically in development, so it would become same-origin XSS.
    """
    assert safe_suffix_for("payload.html", "video") == ".mp4"
    assert safe_suffix_for("payload.php", "image") == ".jpg"
    assert safe_suffix_for("payload.sh", "video") == ".mp4"


def test_safe_suffix_ignores_path_traversal_in_the_filename() -> None:
    assert safe_suffix_for("../../../etc/passwd", "video") == ".mp4"
    assert safe_suffix_for("..\\..\\windows\\evil.exe", "image") == ".jpg"


def test_safe_suffix_keeps_allowed_extensions() -> None:
    assert safe_suffix_for("clip.MOV", "video") == ".mov"
    assert safe_suffix_for("photo.JPEG", "image") == ".jpeg"


def test_safe_suffix_defaults_when_filename_missing() -> None:
    assert safe_suffix_for(None, "image") == ".jpg"
    assert safe_suffix_for("", "video") == ".mp4"


def test_magic_bytes_accept_real_media_headers() -> None:
    assert looks_like_supported_media(b"\xff\xd8\xff\xe0" + b"\x00" * 16)  # JPEG
    assert looks_like_supported_media(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)  # PNG
    assert looks_like_supported_media(b"\x00\x00\x00 ftypisom" + b"\x00" * 8)  # MP4
    assert looks_like_supported_media(b"\x1a\x45\xdf\xa3" + b"\x00" * 16)  # WebM


def test_magic_bytes_reject_scripts_and_html() -> None:
    assert not looks_like_supported_media(b"<html><body>hello</body></html>")
    assert not looks_like_supported_media(b"#!/bin/sh\nrm -rf /\n")
    assert not looks_like_supported_media(b"PK\x03\x04" + b"\x00" * 16)  # zip
    assert not looks_like_supported_media(b"")
    assert not looks_like_supported_media(b"short")


# ─────────────────────────────────────────────────────────────────────────────
# No-detection behaviour
# ─────────────────────────────────────────────────────────────────────────────
class _EmptyTensor:
    """Minimal stand-in for a torch tensor holding zero detections."""

    def __len__(self) -> int:
        return 0

    def cpu(self) -> "_EmptyTensor":
        """Mimic tensor.cpu()."""
        return self

    def numpy(self) -> np.ndarray:
        """Return an empty array, as ultralytics does with no detections."""
        return np.empty((0, 4, 2), dtype=np.float32)


class _EmptyObb:
    """Ultralytics OBB container with no boxes."""

    xyxyxyxy = _EmptyTensor()
    conf = _EmptyTensor()


class _StubYoloResult:
    """Result object reporting zero oriented boxes."""

    obb = _EmptyObb()


class _StubYolo:
    """Ultralytics YOLO stand-in whose inference yields no oriented boxes."""

    def __call__(self, *args: object, **kwargs: object) -> list:
        """Return a single result object carrying zero detections."""
        return [_StubYoloResult()]


class _MalformedYolo:
    """YOLO stand-in returning a result object without the expected fields."""

    def __call__(self, *args: object, **kwargs: object) -> list:
        """Return an object whose ``obb`` lacks polygon/confidence tensors."""

        class _Bad:
            obb = object()

        return [_Bad()]


def _make_unloaded_service():
    """Build an OBBRoiService without running its model-loading constructor."""
    from app.services import obb_roi_service as module

    return module.OBBRoiService.__new__(module.OBBRoiService)


def test_obb_roi_service_reports_not_qualified_when_nothing_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    With no fish in frame the service must return a non-qualified result with a
    reason, never raise and never invent a crop.
    """
    from app.services import obb_roi_service as module

    service = _make_unloaded_service()
    service._model = _StubYolo()
    service.is_loaded = True

    monkeypatch.setattr(
        module.settings, "roi_allow_center_fallback", False, raising=False
    )

    result = service.extract_roi(make_frame())

    assert result.qualified is False
    assert result.roi is None
    assert result.reason == "no detection"


def test_obb_roi_service_survives_a_malformed_model_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A result object missing xyxyxyxy must not raise AttributeError."""
    from app.services import obb_roi_service as module

    service = _make_unloaded_service()
    service._model = _MalformedYolo()
    service.is_loaded = True

    monkeypatch.setattr(
        module.settings, "roi_allow_center_fallback", False, raising=False
    )

    result = service.extract_roi(make_frame())

    assert result.qualified is False
    assert result.reason == "no detection"


def test_obb_roi_service_reports_not_qualified_when_model_is_missing() -> None:
    """An unavailable model must degrade gracefully, not crash the request."""
    service = _make_unloaded_service()
    service._model = None
    service.is_loaded = False

    result = service.extract_roi(make_frame())

    assert result.qualified is False
    assert result.reason
    assert "not loaded" in result.reason.lower()
