"""
OBB ROI extraction.

Every embedding the system compares is computed from the crop this service
produces, so its geometry decides whether two captures of one fish are comparable
at all.

A fish photographed at an angle occupies a diagonal region. An axis-aligned box
around it is mostly water and the pattern is sheared; the oriented box carries the
rotation, so the deskewed crop is normalised the same way every time. If the corner
ordering is wrong the crop comes out mirrored or rotated — and nothing raises,
because a mirrored crop is still a valid image. It simply never matches.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.services import obb_roi_service as module
from app.services.obb_roi_service import (
    OBBRoiService,
    get_loaded_obb_roi_service,
)


def bare_service() -> OBBRoiService:
    """Build a service without running the model-loading constructor."""
    service = OBBRoiService.__new__(OBBRoiService)
    service._model = None
    service.is_loaded = False
    return service


def frame_with_marker(width: int = 640, height: int = 480) -> np.ndarray:
    """
    Build a frame with a distinguishable bright patch in the top-left quadrant.

    Lets a crop's orientation be verified from its content rather than only its
    dimensions.
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[10:60, 10:110] = 255
    return frame


class _Tensor:
    """Minimal stand-in for the torch tensors ultralytics returns."""

    def __init__(self, array: np.ndarray) -> None:
        """Store the backing array."""
        self._array = array

    def __len__(self) -> int:
        return len(self._array)

    def cpu(self) -> "_Tensor":
        """Mimic tensor.cpu()."""
        return self

    def numpy(self) -> np.ndarray:
        """Return the backing array."""
        return self._array


class _Obb:
    """Ultralytics OBB container stand-in."""

    def __init__(self, polygons: np.ndarray, confidences: np.ndarray) -> None:
        """Wrap polygons and confidences as tensor-like objects."""
        self.xyxyxyxy = _Tensor(polygons)
        self.conf = _Tensor(confidences)


class _Result:
    """Ultralytics result stand-in."""

    def __init__(self, polygons: np.ndarray, confidences: np.ndarray) -> None:
        """Attach an OBB container."""
        self.obb = _Obb(polygons, confidences)


class _StubYolo:
    """YOLO stand-in returning fixed detections."""

    def __init__(self, polygons: np.ndarray, confidences: np.ndarray) -> None:
        """Store the detections to return on every call."""
        self._polygons = polygons
        self._confidences = confidences

    def __call__(self, *_args: object, **_kwargs: object) -> list:
        """Return a single result carrying the stored detections."""
        return [_Result(self._polygons, self._confidences)]


def loaded_service(polygons: list[list[tuple[float, float]]], confidences: list[float]):
    """Build a service backed by a stub detector."""
    service = bare_service()
    service._model = _StubYolo(
        np.array(polygons, dtype=np.float32), np.array(confidences, dtype=np.float32)
    )
    service.is_loaded = True
    return service


def rect(x1: float, y1: float, x2: float, y2: float) -> list[tuple[float, float]]:
    """Build an axis-aligned rectangle as four corner points."""
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# ─────────────────────────────────────────────────────────────────────────────
# Corner ordering
# ─────────────────────────────────────────────────────────────────────────────
def test_corner_ordering_normalises_an_already_ordered_box() -> None:
    service = bare_service()
    points = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], dtype=np.float32)

    ordered = service._order_points_clockwise(points)

    np.testing.assert_allclose(ordered, points)


def test_corner_ordering_is_invariant_to_input_rotation() -> None:
    """
    ultralytics does not guarantee which corner comes first. If ordering depended
    on that, the same box could yield a rotated crop between runs.
    """
    service = bare_service()
    canonical = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], dtype=np.float32)

    for shift in range(4):
        rotated = np.roll(canonical, shift, axis=0)
        np.testing.assert_allclose(
            service._order_points_clockwise(rotated), canonical, atol=1e-5
        )


def test_corner_ordering_puts_top_left_first() -> None:
    service = bare_service()
    points = np.array([[100, 50], [0, 50], [100, 0], [0, 0]], dtype=np.float32)

    ordered = service._order_points_clockwise(points)

    assert tuple(ordered[0]) == (0.0, 0.0)
    assert tuple(ordered[2]) == (100.0, 50.0)


# ─────────────────────────────────────────────────────────────────────────────
# Deskew
# ─────────────────────────────────────────────────────────────────────────────
def test_deskew_of_an_axis_aligned_box_returns_its_dimensions() -> None:
    service = bare_service()
    frame = frame_with_marker()
    points = np.array([[100, 200], [300, 200], [300, 260], [100, 260]], dtype=np.float32)

    crop = service._deskew_crop(frame, points)

    assert crop is not None
    assert crop.shape[:2] == (60, 200)


def test_deskew_straightens_a_rotated_box() -> None:
    """
    The whole point: a diagonal fish becomes an axis-aligned crop, so the encoder
    always sees the same presentation.
    """
    service = bare_service()
    frame = frame_with_marker()
    # A 200x60 box rotated roughly 30 degrees.
    points = np.array(
        [[100, 200], [273, 300], [243, 352], [70, 252]], dtype=np.float32
    )

    crop = service._deskew_crop(frame, points)

    assert crop is not None
    height, width = crop.shape[:2]
    assert width > height


def test_deskew_returns_none_for_a_degenerate_box() -> None:
    service = bare_service()
    points = np.array([[10, 10], [10, 10], [10, 10], [10, 10]], dtype=np.float32)

    assert service._deskew_crop(frame_with_marker(), points) is None


def test_deskew_preserves_three_channels() -> None:
    service = bare_service()
    points = np.array([[0, 0], [200, 0], [200, 100], [0, 100]], dtype=np.float32)

    crop = service._deskew_crop(frame_with_marker(), points)

    assert crop is not None
    assert crop.shape[2] == 3


def test_deskew_accepts_a_python_list_of_points() -> None:
    """Points arrive as lists from the tracking path and as arrays from the detector."""
    service = bare_service()

    crop = service._deskew_crop(frame_with_marker(), rect(0, 0, 150, 80))

    assert crop is not None
    assert crop.shape[:2] == (80, 150)


# ─────────────────────────────────────────────────────────────────────────────
# Detection selection
# ─────────────────────────────────────────────────────────────────────────────
def test_a_single_good_detection_qualifies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "roi_require_single_detection", True, raising=False)
    monkeypatch.setattr(settings, "roi_min_side_px", 48, raising=False)
    service = loaded_service([rect(100, 100, 400, 260)], [0.91])

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is True
    assert result.roi is not None
    assert result.confidence == pytest.approx(0.91)


def test_multiple_detections_are_rejected_when_single_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Two fish in frame means the crop could belong to either, and a wrong
    attribution merges two identities permanently.
    """
    monkeypatch.setattr(settings, "roi_require_single_detection", True, raising=False)
    service = loaded_service(
        [rect(50, 50, 200, 130), rect(300, 200, 500, 300)], [0.9, 0.8]
    )

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is False
    assert "detections" in result.reason


def test_multiple_detections_pick_the_most_confident_when_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "roi_require_single_detection", False, raising=False)
    monkeypatch.setattr(settings, "roi_min_side_px", 10, raising=False)
    service = loaded_service(
        [rect(50, 50, 200, 130), rect(300, 200, 500, 300)], [0.4, 0.95]
    )

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is True
    assert result.confidence == pytest.approx(0.95)


def test_a_roi_below_the_minimum_side_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A tiny ROI upscaled to the model input is mostly interpolation, which the
    encoder would read as pattern.
    """
    monkeypatch.setattr(settings, "roi_require_single_detection", True, raising=False)
    monkeypatch.setattr(settings, "roi_min_side_px", 48, raising=False)
    service = loaded_service([rect(100, 100, 130, 120)], [0.9])

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is False
    assert "too small" in result.reason


def test_no_detection_reports_a_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "roi_allow_center_fallback", False, raising=False)
    service = loaded_service([], [])
    # An empty polygon array must still have the right dimensionality.
    service._model = _StubYolo(
        np.empty((0, 4, 2), dtype=np.float32), np.empty((0,), dtype=np.float32)
    )

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is False
    assert result.reason == "no detection"


def test_inference_failure_degrades_to_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model crash must not abort the job; the frame is simply unusable."""

    class _Exploding:
        def __call__(self, *_a: object, **_k: object) -> list:
            raise RuntimeError("cuda oom")

    service = bare_service()
    service._model = _Exploding()
    service.is_loaded = True

    result = service.extract_roi(frame_with_marker())

    assert result.qualified is False
    assert "inference error" in result.reason


def test_unloaded_model_reports_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "roi_allow_center_fallback", False, raising=False)

    result = bare_service().extract_roi(frame_with_marker())

    assert result.qualified is False
    assert "not loaded" in result.reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Centre-crop fallback
# ─────────────────────────────────────────────────────────────────────────────
def test_center_crop_fallback_takes_the_middle_seventy_percent() -> None:
    service = bare_service()

    result = service._center_crop_fallback(frame_with_marker(640, 480), reason="test")

    assert result.qualified is True
    assert result.roi is not None
    assert result.roi.shape[:2] == (480 - 2 * 72, 640 - 2 * 96)


def test_center_crop_fallback_reports_zero_confidence() -> None:
    """
    There was no detection, so no confidence exists. Reporting a non-zero value
    would let a guessed crop look like a real one downstream.
    """
    result = bare_service()._center_crop_fallback(frame_with_marker(), reason="test")

    assert result.confidence == 0.0
    assert "fallback" in result.reason


def test_center_crop_fallback_is_used_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Off by default and documented as unsafe: centre crops produce noisy embeddings
    that degrade matching for every future comparison.
    """
    monkeypatch.setattr(settings, "roi_allow_center_fallback", True, raising=False)

    result = bare_service().extract_roi(frame_with_marker())

    assert result.qualified is True
    assert "fallback" in result.reason


# ─────────────────────────────────────────────────────────────────────────────
# Non-forcing accessor
# ─────────────────────────────────────────────────────────────────────────────
def test_loaded_accessor_does_not_construct_the_service() -> None:
    original = module._obb_roi_service
    module._obb_roi_service = None
    try:
        assert get_loaded_obb_roi_service() is None
    finally:
        module._obb_roi_service = original
