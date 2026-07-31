"""
Capture artifact storage.

Artifacts are the durable evidence behind an identification: the ROI crops a
researcher inspects when auditing a match, and the per-fish index that lists every
capture of one animal.

The index is the interesting part. It is written *after* the database transaction
commits, precisely so a rolled-back transaction cannot leave a phantom capture in
it, and it must be idempotent: reprocessing a job has to replace that job's entry
rather than append a duplicate, or the capture count drifts upward on every retry.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.services.artifact_service import (
    _now_iso,
    _storage_url,
    _write_jpg,
    update_fish_index_file,
)


def bgr(width: int = 64, height: int = 48, value: int = 120) -> np.ndarray:
    """Build a uniform BGR frame."""
    return np.full((height, width, 3), value, dtype=np.uint8)


def index_entry(job_id: str, catch_number: int, **overrides: object) -> dict:
    """Build a fish-index capture entry."""
    entry = {
        "job_id": job_id,
        "sighting_id": f"sighting-{job_id}",
        "fish_id": "CZ-401001-CYPCA-0001",
        "area_code": "401001",
        "species_slug": "cyprinus_carpio",
        "catch_number": catch_number,
        "is_new_fish": catch_number == 1,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    entry.update(overrides)
    return entry


def read_index(path: Path) -> dict:
    """Read and parse the fish index."""
    return json.loads(path.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# JPEG writing
# ─────────────────────────────────────────────────────────────────────────────
def test_write_jpg_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Artifact paths nest several levels deep and are created on demand."""
    target = tmp_path / "a" / "b" / "c" / "crop.jpg"

    _write_jpg(target, bgr())

    assert target.is_file()


def test_write_jpg_produces_a_decodable_jpeg(tmp_path: Path) -> None:
    import cv2

    target = tmp_path / "crop.jpg"
    _write_jpg(target, bgr(width=32, height=24))

    decoded = cv2.imread(str(target))

    assert decoded is not None
    assert decoded.shape == (24, 32, 3)


def test_write_jpg_starts_with_the_jpeg_magic_bytes(tmp_path: Path) -> None:
    target = tmp_path / "crop.jpg"

    _write_jpg(target, bgr())

    assert target.read_bytes().startswith(b"\xff\xd8\xff")


def test_write_jpg_honours_an_explicit_quality(tmp_path: Path) -> None:
    """
    Quality is configurable because crops feed the encoder: over-compression
    destroys the spot detail matching depends on.
    """
    high = tmp_path / "high.jpg"
    low = tmp_path / "low.jpg"
    # A noisy image so quality actually changes the encoded size.
    rng = np.random.default_rng(0)
    noisy = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    _write_jpg(high, noisy, quality=95)
    _write_jpg(low, noisy, quality=20)

    assert high.stat().st_size > low.stat().st_size


def test_write_jpg_raises_on_an_unwritable_path(tmp_path: Path) -> None:
    """
    Must raise rather than silently skip: the caller treats artifact writes as
    best-effort, but it needs to know one failed in order to log it.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")

    with pytest.raises((RuntimeError, OSError, NotADirectoryError)):
        _write_jpg(blocker / "nested" / "crop.jpg", bgr())


# ─────────────────────────────────────────────────────────────────────────────
# Storage URLs
# ─────────────────────────────────────────────────────────────────────────────
def test_storage_url_is_prefixed_with_the_mount_point() -> None:
    assert _storage_url("jobs/abc/preview.jpg") == "/storage/jobs/abc/preview.jpg"


def test_storage_url_normalises_windows_separators() -> None:
    """
    Paths are built with pathlib, which uses backslashes on Windows. A URL with
    backslashes does not resolve.
    """
    assert _storage_url("jobs\\abc\\preview.jpg") == "/storage/jobs/abc/preview.jpg"


def test_storage_url_of_none_is_none() -> None:
    """An absent artifact must serialise as null, not as '/storage/None'."""
    assert _storage_url(None) is None


def test_storage_url_of_an_empty_string_is_none() -> None:
    assert _storage_url("") is None


# ─────────────────────────────────────────────────────────────────────────────
# Timestamps
# ─────────────────────────────────────────────────────────────────────────────
def test_now_iso_is_timezone_aware_utc() -> None:
    """
    A naive timestamp cannot be compared across deployments, and these values are
    used to order a fish's capture history.
    """
    from datetime import datetime

    parsed = datetime.fromisoformat(_now_iso())

    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


# ─────────────────────────────────────────────────────────────────────────────
# Fish index
# ─────────────────────────────────────────────────────────────────────────────
def test_index_is_created_on_the_first_capture(tmp_path: Path) -> None:
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))

    document = read_index(path)
    assert document["fish_id"] == "CZ-401001-CYPCA-0001"
    assert document["total_captures"] == 1


def test_index_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "private" / "fish_documents" / "401001" / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))

    assert path.is_file()


def test_index_appends_a_second_capture(tmp_path: Path) -> None:
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))
    update_fish_index_file(path, index_entry("job-2", 2))

    document = read_index(path)
    assert document["total_captures"] == 2
    assert [c["job_id"] for c in document["captures"]] == ["job-1", "job-2"]


def test_reprocessing_a_job_replaces_its_entry_rather_than_duplicating(
    tmp_path: Path,
) -> None:
    """
    The idempotency guarantee. Without it, every forced reprocess would inflate the
    capture count for that fish.
    """
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))
    update_fish_index_file(path, index_entry("job-1", 1, sighting_id="rerun"))

    document = read_index(path)
    assert document["total_captures"] == 1
    assert document["captures"][0]["sighting_id"] == "rerun"


def test_captures_are_ordered_by_catch_number(tmp_path: Path) -> None:
    """The history is read in order; insertion order is not guaranteed."""
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-3", 3))
    update_fish_index_file(path, index_entry("job-1", 1))
    update_fish_index_file(path, index_entry("job-2", 2))

    document = read_index(path)
    assert [c["catch_number"] for c in document["captures"]] == [1, 2, 3]


def test_index_carries_a_schema_version(tmp_path: Path) -> None:
    """The document is long-lived on disk, so it must be versioned to migrate."""
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))

    assert read_index(path)["schema_version"] == "1.0"


def test_index_records_an_update_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))

    from datetime import datetime

    assert datetime.fromisoformat(read_index(path)["updated_at"]).tzinfo is not None


def test_a_corrupt_index_is_rebuilt_rather_than_crashing(tmp_path: Path) -> None:
    """
    Written post-commit and unguarded by a transaction, so a process killed
    mid-write leaves a truncated file. Losing the index is acceptable — it is
    derivable from the database — but failing the write is not.
    """
    path = tmp_path / "fish_index.json"
    path.write_text('{"captures": [ truncated', encoding="utf-8")

    update_fish_index_file(path, index_entry("job-1", 1))

    document = read_index(path)
    assert document["total_captures"] == 1


def test_an_index_without_a_captures_key_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "fish_index.json"
    path.write_text('{"schema_version": "0.9"}', encoding="utf-8")

    update_fish_index_file(path, index_entry("job-1", 1))

    assert read_index(path)["total_captures"] == 1


def test_index_preserves_non_ascii_species_names(tmp_path: Path) -> None:
    """Czech names carry diacritics; escaping them would corrupt the record."""
    path = tmp_path / "fish_index.json"

    update_fish_index_file(
        path, index_entry("job-1", 1, species_czech="Kapr obecný")
    )

    raw = path.read_text(encoding="utf-8")
    assert "obecný" in raw


def test_index_is_written_as_indented_json(tmp_path: Path) -> None:
    """Operators read this file by hand when auditing a match."""
    path = tmp_path / "fish_index.json"

    update_fish_index_file(path, index_entry("job-1", 1))

    assert "\n  " in path.read_text(encoding="utf-8")


def test_total_captures_always_matches_the_list_length(tmp_path: Path) -> None:
    path = tmp_path / "fish_index.json"

    for catch in range(1, 6):
        update_fish_index_file(path, index_entry(f"job-{catch}", catch))
    # A reprocess of an existing job must not change the count.
    update_fish_index_file(path, index_entry("job-3", 3))

    document = read_index(path)
    assert document["total_captures"] == len(document["captures"]) == 5
