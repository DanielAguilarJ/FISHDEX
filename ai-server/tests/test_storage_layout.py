"""
Disk storage layout.

The storage tree caches ROI crops and embeddings for the matching pipeline:

    {data_dir}/{area_code}/{species_slug}/{fish_id}/catch_N/images/
                                                            + data.json

SQLite remains the authoritative source of truth; this tree is a rebuildable
cache. The read paths tested here back the area statistics and fish-history
endpoints, and every one of them walks untrusted directory contents — a stray file
or a hand-edited name must not raise.

``base_dir()`` is resolved per call rather than captured at import, which is what
makes these tests possible: the previous module-level constant froze the path at
first import and ignored any later configuration change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.services.storage_service import (
    base_dir,
    get_area_stats,
    get_disk_usage_mb,
    get_fish_history,
    get_fish_history_by_id,
    get_species_in_area,
    get_total_fish_count,
)


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the storage root at a temporary directory."""
    root = tmp_path / "server-data"
    root.mkdir()
    monkeypatch.setattr(settings, "server_data_dir", str(root), raising=False)
    return root


def add_catch(
    root: Path,
    area: str,
    species: str,
    fish_id: str,
    catch: int = 1,
    *,
    images: int = 3,
    saved_at: str = "2026-01-01T10:00:00+00:00",
    extra: dict | None = None,
) -> Path:
    """
    Create one catch directory with images and a data.json.

    Args:
        root: Storage root.
        area: Area code directory name.
        species: Species slug directory name.
        fish_id: Fish identifier directory name.
        catch: Catch sequence number.
        images: How many placeholder frames to write.
        saved_at: Timestamp recorded in data.json.
        extra: Additional fields merged into data.json.

    Returns:
        The catch directory.
    """
    catch_dir = root / area / species / fish_id / f"catch_{catch}"
    images_dir = catch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for index in range(images):
        (images_dir / f"frame_{index}.jpg").write_bytes(b"\xff\xd8\xff")

    payload: dict = {"saved_at": saved_at, "fish_id": fish_id, "catch_number": catch}
    if extra:
        payload.update(extra)
    (catch_dir / "data.json").write_text(json.dumps(payload), encoding="utf-8")
    return catch_dir


# ─────────────────────────────────────────────────────────────────────────────
# base_dir resolution
# ─────────────────────────────────────────────────────────────────────────────
def test_base_dir_follows_the_current_configuration(storage: Path) -> None:
    """
    The regression this fixes: a module-level constant captured the path at import
    and ignored every later change.
    """
    assert base_dir() == storage


def test_base_dir_reflects_a_later_reconfiguration(
    storage: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = tmp_path / "relocated"
    monkeypatch.setattr(settings, "server_data_dir", str(moved), raising=False)

    assert base_dir() == moved


# ─────────────────────────────────────────────────────────────────────────────
# get_species_in_area
# ─────────────────────────────────────────────────────────────────────────────
def test_species_in_area_lists_each_species_once(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0002")
    add_catch(storage, "401001", "esox_lucius", "CZ-401001-ESOLU-0001")

    assert sorted(get_species_in_area("401001")) == ["cyprinus_carpio", "esox_lucius"]


def test_species_in_area_accepts_a_spaced_area_code(storage: Path) -> None:
    """Czech revír codes are written both ways; both must resolve to one directory."""
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    assert get_species_in_area("401 001") == ["cyprinus_carpio"]


def test_species_in_area_is_empty_for_an_unknown_area(storage: Path) -> None:
    assert get_species_in_area("999999") == []


def test_species_in_area_ignores_stray_files(storage: Path) -> None:
    """A file where a species directory is expected must not raise."""
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    (storage / "401001" / "README.txt").write_text("not a species", encoding="utf-8")

    assert get_species_in_area("401001") == ["cyprinus_carpio"]


# ─────────────────────────────────────────────────────────────────────────────
# get_area_stats
# ─────────────────────────────────────────────────────────────────────────────
def test_area_stats_counts_distinct_fish_not_catches(storage: Path) -> None:
    """
    Two catches of one fish is one fish. Conflating them would overstate the
    population, which is the number the research view reports.
    """
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=1)
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=2)
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0002", catch=1)

    stats = get_area_stats("401001")

    assert stats["total_fish"] == 2
    assert stats["total_catches"] == 3


def test_area_stats_breaks_down_by_species(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0002")
    add_catch(storage, "401001", "esox_lucius", "CZ-401001-ESOLU-0001")

    stats = get_area_stats("401001")

    assert stats["species_breakdown"] == {"cyprinus_carpio": 2, "esox_lucius": 1}


def test_area_stats_reports_the_latest_catch_timestamp(storage: Path) -> None:
    add_catch(
        storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001",
        catch=1, saved_at="2026-01-01T10:00:00+00:00",
    )
    add_catch(
        storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001",
        catch=2, saved_at="2026-06-15T18:30:00+00:00",
    )

    assert get_area_stats("401001")["most_recent_catch"] == "2026-06-15T18:30:00+00:00"


def test_area_stats_are_zeroed_for_an_unknown_area(storage: Path) -> None:
    stats = get_area_stats("999999")

    assert stats["total_fish"] == 0
    assert stats["total_catches"] == 0
    assert stats["species_breakdown"] == {}


def test_area_stats_survive_a_corrupt_data_file(storage: Path) -> None:
    """
    A truncated data.json must be skipped, not crash the endpoint. It is a
    rebuildable cache, so partial data is expected after an interrupted write.
    """
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    catch_dir = add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0002")
    (catch_dir / "data.json").write_text("{ truncated", encoding="utf-8")

    stats = get_area_stats("401001")

    assert stats["total_fish"] == 2


def test_area_stats_handle_a_catch_without_a_data_file(storage: Path) -> None:
    fish_dir = storage / "401001" / "cyprinus_carpio" / "CZ-401001-CYPCA-0001"
    (fish_dir / "catch_1" / "images").mkdir(parents=True)

    assert get_area_stats("401001")["total_fish"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_fish_history
# ─────────────────────────────────────────────────────────────────────────────
def test_fish_history_is_ordered_by_catch_number(storage: Path) -> None:
    for catch in (3, 1, 2):
        add_catch(
            storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=catch
        )

    history = get_fish_history("401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    assert [entry["catch_number"] for entry in history] == [1, 2, 3]


def test_fish_history_counts_the_stored_images(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", images=5)

    history = get_fish_history("401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    assert history[0]["images_count"] == 5


def test_fish_history_is_empty_for_an_unknown_fish(storage: Path) -> None:
    assert get_fish_history("401001", "cyprinus_carpio", "CZ-401001-NOPE-9999") == []


def test_fish_history_skips_an_unreadable_record(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=1)
    bad = add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=2)
    (bad / "data.json").write_text("not json at all", encoding="utf-8")

    history = get_fish_history("401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    assert len(history) == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_fish_history_by_id
# ─────────────────────────────────────────────────────────────────────────────
def test_history_by_id_finds_a_fish_across_areas(storage: Path) -> None:
    """The caller often knows only the fish id, so the scan spans every area."""
    add_catch(storage, "471011", "esox_lucius", "CZ-471011-ESOLU-0007", catch=1)
    add_catch(storage, "471011", "esox_lucius", "CZ-471011-ESOLU-0007", catch=2)

    result = get_fish_history_by_id("CZ-471011-ESOLU-0007")

    assert result is not None
    assert result["area_code"] == "471011"
    assert result["species_slug"] == "esox_lucius"
    assert result["total_catches"] == 2


def test_history_by_id_returns_none_when_absent(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    assert get_fish_history_by_id("CZ-401001-CYPCA-9999") is None


def test_history_by_id_returns_none_on_an_empty_store(storage: Path) -> None:
    assert get_fish_history_by_id("CZ-401001-CYPCA-0001") is None


def test_history_by_id_ignores_stray_files_while_scanning(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    (storage / "stray.txt").write_text("x", encoding="utf-8")

    assert get_fish_history_by_id("CZ-401001-CYPCA-0001") is not None


def test_history_by_id_total_matches_the_history_length(storage: Path) -> None:
    for catch in (1, 2, 3):
        add_catch(
            storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=catch
        )

    result = get_fish_history_by_id("CZ-401001-CYPCA-0001")

    assert result is not None
    assert result["total_catches"] == len(result["history"])


# ─────────────────────────────────────────────────────────────────────────────
# Aggregates
# ─────────────────────────────────────────────────────────────────────────────
def test_total_fish_count_spans_areas_and_species(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    add_catch(storage, "401001", "esox_lucius", "CZ-401001-ESOLU-0001")
    add_catch(storage, "471011", "cyprinus_carpio", "CZ-471011-CYPCA-0001")

    assert get_total_fish_count() == 3


def test_total_fish_count_does_not_double_count_catches(storage: Path) -> None:
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=1)
    add_catch(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catch=2)

    assert get_total_fish_count() == 1


def test_total_fish_count_is_zero_on_an_empty_store(storage: Path) -> None:
    assert get_total_fish_count() == 0


def test_disk_usage_grows_with_stored_bytes(storage: Path) -> None:
    baseline = get_disk_usage_mb()
    (storage / "big.bin").write_bytes(b"\x00" * (2 * 1024 * 1024))

    assert get_disk_usage_mb() > baseline


def test_disk_usage_is_zero_on_an_empty_store(storage: Path) -> None:
    assert get_disk_usage_mb() == 0.0


def test_disk_usage_is_reported_in_megabytes(storage: Path) -> None:
    (storage / "one_mb.bin").write_bytes(b"\x00" * (1024 * 1024))

    assert get_disk_usage_mb() == pytest.approx(1.0, abs=0.05)
