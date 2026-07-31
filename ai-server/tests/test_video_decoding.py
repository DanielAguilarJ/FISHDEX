"""
Video decoding and frame selection.

Everything downstream of this module sees only the frames it emits, so a defect
here is invisible to the rest of the pipeline: a wrongly rotated frame produces a
valid-looking but incomparable embedding, and an over-eager resize destroys the
spot detail that re-identification depends on.

These tests write real video files with OpenCV rather than mocking the decoder,
because the behaviour under test *is* the decoder integration — frame counts,
rotation handling and aspect preservation.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.utils.video import (
    _apply_video_rotation,
    _resize_preserve_aspect,
    cleanup_temp_file,
    extract_frames_from_video,
    get_video_info,
    iter_frames_from_video,
    save_temp_video,
    select_best_frame,
    select_best_n_frames,
)


def write_video(
    path: Path,
    *,
    frames: int = 10,
    width: int = 320,
    height: int = 240,
    fps: int = 10,
) -> Path:
    """
    Write a real video file whose frames differ from one another.

    Args:
        path: Destination file (``.mp4``).
        frames: Number of frames to write.
        width: Frame width.
        height: Frame height.
        fps: Frames per second recorded in the container.

    Returns:
        The written path.
    """
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    assert writer.isOpened(), "OpenCV could not open a writer for mp4v"
    try:
        for index in range(frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            # A moving bright square makes frames distinguishable and sharp.
            x = (index * 17) % max(1, width - 40)
            frame[20:60, x : x + 40] = 255
            writer.write(frame)
    finally:
        writer.release()
    return path


def sharp_frame(width: int = 320, height: int = 240) -> np.ndarray:
    """Build a high-contrast frame with a large Laplacian variance."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[::4] = 255
    return frame


def flat_frame(width: int = 320, height: int = 240, value: int = 128) -> np.ndarray:
    """Build a uniform frame with near-zero Laplacian variance."""
    return np.full((height, width, 3), value, dtype=np.uint8)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    """A 10-frame 320x240 test video."""
    return write_video(tmp_path / "clip.mp4")


# ─────────────────────────────────────────────────────────────────────────────
# Aspect-preserving resize
# ─────────────────────────────────────────────────────────────────────────────
def test_resize_caps_the_longest_side() -> None:
    frame = np.zeros((480, 1920, 3), dtype=np.uint8)

    resized = _resize_preserve_aspect(frame, max_side=960)

    assert max(resized.shape[:2]) == 960


def test_resize_preserves_the_aspect_ratio() -> None:
    """
    A distorted frame yields a distorted crop, and the encoder was trained on
    undistorted ROIs.
    """
    frame = np.zeros((480, 1920, 3), dtype=np.uint8)

    resized = _resize_preserve_aspect(frame, max_side=960)
    height, width = resized.shape[:2]

    assert width / height == pytest.approx(1920 / 480, rel=0.02)


def test_resize_does_not_upscale_a_small_frame() -> None:
    """Upscaling invents detail; the encoder would read interpolation as pattern."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    assert _resize_preserve_aspect(frame, max_side=960).shape == frame.shape


def test_resize_does_not_force_landscape() -> None:
    """A portrait capture must stay portrait — rotating it would break matching."""
    frame = np.zeros((1920, 480, 3), dtype=np.uint8)

    resized = _resize_preserve_aspect(frame, max_side=960)

    assert resized.shape[0] > resized.shape[1]


def test_resize_handles_a_square_frame() -> None:
    frame = np.zeros((1000, 1000, 3), dtype=np.uint8)

    assert _resize_preserve_aspect(frame, max_side=500).shape[:2] == (500, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Rotation
# ─────────────────────────────────────────────────────────────────────────────
def test_zero_rotation_returns_the_frame_unchanged() -> None:
    frame = sharp_frame()

    assert np.array_equal(_apply_video_rotation(frame, 0), frame)


@pytest.mark.parametrize(("rotation", "swaps"), [(90, True), (180, False), (270, True)])
def test_rotation_swaps_dimensions_only_for_quarter_turns(
    rotation: int, swaps: bool
) -> None:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    rotated = _apply_video_rotation(frame, rotation)

    if swaps:
        assert rotated.shape[:2] == (320, 240)
    else:
        assert rotated.shape[:2] == (240, 320)


def test_four_quarter_turns_return_to_the_original() -> None:
    """Guards against a sign error in the rotation direction."""
    frame = sharp_frame(width=64, height=48)

    rotated = frame
    for _ in range(4):
        rotated = _apply_video_rotation(rotated, 90)

    assert np.array_equal(rotated, frame)


def test_unknown_rotation_is_ignored() -> None:
    """An unexpected metadata value must not corrupt the frame."""
    frame = sharp_frame()

    assert np.array_equal(_apply_video_rotation(frame, 45), frame)


# ─────────────────────────────────────────────────────────────────────────────
# Decoding
# ─────────────────────────────────────────────────────────────────────────────
def test_iter_frames_yields_every_frame_with_metadata(video: Path) -> None:
    decoded = list(iter_frames_from_video(str(video)))

    assert len(decoded) > 0
    assert [d.frame_index for d in decoded] == sorted(d.frame_index for d in decoded)
    assert all(d.frame is not None for d in decoded)


def test_iter_frames_timestamps_increase_monotonically(video: Path) -> None:
    """Temporal diversity selection compares timestamps; they must be ordered."""
    timestamps = [d.timestamp_seconds for d in iter_frames_from_video(str(video))]

    assert timestamps == sorted(timestamps)


def test_iter_frames_applies_the_size_cap(tmp_path: Path) -> None:
    write_video(tmp_path / "big.mp4", width=1280, height=720, frames=3)

    decoded = list(iter_frames_from_video(str(tmp_path / "big.mp4"), max_side=320))

    assert all(max(d.frame.shape[:2]) <= 320 for d in decoded)


def test_iter_frames_raises_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No se pudo abrir"):
        list(iter_frames_from_video(str(tmp_path / "absent.mp4")))


def test_iter_frames_raises_for_a_non_video_file(tmp_path: Path) -> None:
    junk = tmp_path / "not-a-video.mp4"
    junk.write_bytes(b"this is not a video")

    with pytest.raises(ValueError):
        list(iter_frames_from_video(str(junk)))


def test_extract_frames_respects_the_maximum(video: Path) -> None:
    frames = extract_frames_from_video(str(video), max_frames=3)

    assert 0 < len(frames) <= 3


def test_extract_frames_samples_across_the_clip(tmp_path: Path) -> None:
    """
    Sampling only the opening frames would miss the fish entirely on a capture
    where the angler lifts it mid-clip.
    """
    write_video(tmp_path / "long.mp4", frames=40)

    frames = extract_frames_from_video(str(tmp_path / "long.mp4"), max_frames=5)

    assert len(frames) == 5
    # Distinct content proves they are not five copies of frame 0.
    assert len({frame.tobytes() for frame in frames}) > 1


def test_extract_frames_returns_all_when_fewer_than_requested(tmp_path: Path) -> None:
    write_video(tmp_path / "short.mp4", frames=3)

    frames = extract_frames_from_video(str(tmp_path / "short.mp4"), max_frames=10)

    assert 0 < len(frames) <= 3


def test_extract_frames_applies_the_size_cap(tmp_path: Path) -> None:
    write_video(tmp_path / "hd.mp4", width=1280, height=720, frames=5)

    frames = extract_frames_from_video(str(tmp_path / "hd.mp4"), max_side=200)

    assert all(max(f.shape[:2]) <= 200 for f in frames)


# ─────────────────────────────────────────────────────────────────────────────
# Frame selection
# ─────────────────────────────────────────────────────────────────────────────
def test_best_frame_is_the_sharpest() -> None:
    """A blurred frame produces a weaker embedding, so sharpness is the criterion."""
    chosen = select_best_frame([flat_frame(), sharp_frame(), flat_frame(value=200)])

    assert np.array_equal(chosen, sharp_frame())


def test_best_frame_of_a_single_frame_is_that_frame() -> None:
    only = sharp_frame()

    assert np.array_equal(select_best_frame([only]), only)


def test_best_n_frames_returns_at_most_n() -> None:
    frames = [flat_frame(value=v) for v in range(10, 200, 10)]

    assert len(select_best_n_frames(frames, n=4)) == 4


def test_best_n_frames_returns_all_when_fewer_exist() -> None:
    frames = [sharp_frame(), flat_frame()]

    assert len(select_best_n_frames(frames, n=5)) == 2


def test_best_n_frames_prefers_sharp_over_flat() -> None:
    frames = [flat_frame(), flat_frame(value=60), sharp_frame()]

    selected = select_best_n_frames(frames, n=1)

    assert np.array_equal(selected[0], sharp_frame())


def test_best_n_frames_on_an_empty_list() -> None:
    assert select_best_n_frames([], n=3) == []


# ─────────────────────────────────────────────────────────────────────────────
# Temp files
# ─────────────────────────────────────────────────────────────────────────────
def test_save_temp_video_writes_the_bytes_verbatim() -> None:
    payload = b"\x00\x00\x00 ftypisom" + b"\x01" * 64

    path = save_temp_video(payload, suffix=".mp4")
    try:
        assert Path(path).read_bytes() == payload
    finally:
        cleanup_temp_file(path)


def test_save_temp_video_honours_the_suffix() -> None:
    """ffmpeg and OpenCV pick a demuxer from the extension, so it must survive."""
    path = save_temp_video(b"\x00" * 32, suffix=".mov")
    try:
        assert path.endswith(".mov")
    finally:
        cleanup_temp_file(path)


def test_cleanup_removes_the_file() -> None:
    path = save_temp_video(b"\x00" * 16, suffix=".mp4")

    cleanup_temp_file(path)

    assert not os.path.exists(path)


def test_cleanup_of_a_missing_file_is_silent() -> None:
    """Called from a finally block, so it must never mask the original error."""
    cleanup_temp_file("/tmp/fishdex-does-not-exist-12345.mp4")


def test_cleanup_of_a_directory_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="app.utils.video"):
        cleanup_temp_file(str(tmp_path))

    assert any("Could not remove temp file" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────────────────────────────────────
def test_video_info_reports_dimensions_and_duration(video: Path) -> None:
    info = get_video_info(str(video))

    assert info["width"] == 320
    assert info["height"] == 240
    assert info["duration_seconds"] > 0


def test_video_info_reports_a_plausible_frame_count(video: Path) -> None:
    info = get_video_info(str(video))

    assert info["total_frames"] > 0


def test_video_info_duration_matches_frames_over_fps(video: Path) -> None:
    """Duration drives the max-length rejection, so it must be derived correctly."""
    info = get_video_info(str(video))

    expected = info["total_frames"] / info["fps"]

    assert info["duration_seconds"] == pytest.approx(expected, rel=0.05)


def test_video_info_reports_the_rotation_metadata(video: Path) -> None:
    """Rotation is read from container metadata and drives frame correction."""
    info = get_video_info(str(video))

    assert info["rotation"] in (0, 90, 180, 270)


def test_video_info_returns_an_error_for_an_unopenable_file(tmp_path: Path) -> None:
    """
    Returns an error dict rather than raising, because the caller uses it to reject
    the upload with a 400 rather than a 500.
    """
    junk = tmp_path / "broken.mp4"
    junk.write_bytes(b"not a video")

    info = get_video_info(str(junk))

    assert "error" in info


def test_video_info_duration_is_zero_when_fps_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container reporting fps=0 must not divide by zero."""
    import app.utils.video as video_module

    class _ZeroFpsCapture:
        """Capture stand-in reporting a zero frame rate."""

        def isOpened(self) -> bool:  # noqa: N802 — mirrors the OpenCV API
            """Report the capture as open."""
            return True

        def get(self, prop: int) -> float:
            """Return 0.0 for every property, including fps."""
            return 0.0

        def release(self) -> None:
            """No-op release."""

    monkeypatch.setattr(video_module.cv2, "VideoCapture", lambda _p: _ZeroFpsCapture())
    monkeypatch.setattr(video_module, "_probe_video_rotation", lambda _p: 0)

    assert get_video_info("irrelevant.mp4")["duration_seconds"] == 0
