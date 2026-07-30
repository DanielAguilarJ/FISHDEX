"""
Dataset split integrity.

The preprocessing split used to shuffle per image, so several frames of the same
physical fish could land in train *and* validation. Augmentation then wrote
derived copies of validation images into the training set. Both inflate reported
accuracy without improving the model, and the failure is silent — hence these
tests.

Run from the repository root:  python -m pytest scripts/tests/test_preprocess_split.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

# scripts/ is not an installable package; add it to the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preprocess import group_key_for, split_dataset  # noqa: E402


def make_paths(spec: dict[str, int]) -> list[Path]:
    """
    Build synthetic dataset paths.

    Args:
        spec: Mapping of clip identifier to number of key frames.

    Returns:
        Paths shaped like the real dataset (``<clip>_kf_<frame>.jpg``).
    """
    return [
        Path(f"/data/carp/{clip}_kf_{index:03d}.jpg")
        for clip, frames in spec.items()
        for index in range(frames)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# group_key_for
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("00fa47d5-003_kf_007.jpg", "00fa47d5-003"),
        ("clip12_kf_000.png", "clip12"),
        ("fish99_003.jpg", "fish99"),
        ("single.jpg", "single"),
    ],
)
def test_group_key_extraction(filename: str, expected: str) -> None:
    assert group_key_for(Path(f"/data/{filename}")) == expected


def test_all_frames_of_one_clip_share_a_group() -> None:
    paths = make_paths({"clipA": 10})
    assert len({group_key_for(p) for p in paths}) == 1


# ─────────────────────────────────────────────────────────────────────────────
# split_dataset — leakage
# ─────────────────────────────────────────────────────────────────────────────
def test_grouped_split_never_leaks_an_identity_across_sets() -> None:
    """No identity may appear in more than one of train/val/test."""
    random.seed(1234)
    paths = make_paths({f"clip{i:02d}": 8 for i in range(30)})

    train, val, test = split_dataset(paths)

    train_ids = {group_key_for(p) for p in train}
    val_ids = {group_key_for(p) for p in val}
    test_ids = {group_key_for(p) for p in test}

    assert train_ids.isdisjoint(val_ids)
    assert train_ids.isdisjoint(test_ids)
    assert val_ids.isdisjoint(test_ids)


def test_grouped_split_preserves_every_file_exactly_once() -> None:
    random.seed(7)
    paths = make_paths({f"clip{i:02d}": 5 for i in range(20)})

    train, val, test = split_dataset(paths)
    combined = train + val + test

    assert len(combined) == len(paths)
    assert set(combined) == set(paths)


def test_grouped_split_is_reproducible_for_a_fixed_seed() -> None:
    """
    Sorting the group keys before shuffling makes the split independent of
    filesystem ordering, so a rerun with the same seed reproduces it exactly.
    """
    paths = make_paths({f"clip{i:02d}": 4 for i in range(15)})

    random.seed(99)
    first = split_dataset(paths)
    random.seed(99)
    second = split_dataset(list(reversed(paths)))

    assert [sorted(map(str, part)) for part in first] == [
        sorted(map(str, part)) for part in second
    ]


def test_grouped_split_populates_all_three_sets() -> None:
    random.seed(3)
    paths = make_paths({f"clip{i:02d}": 6 for i in range(20)})

    train, val, test = split_dataset(paths)

    assert train and val and test


def test_grouped_split_keeps_train_non_empty_with_few_groups() -> None:
    random.seed(5)
    paths = make_paths({"a": 2, "b": 2, "c": 2})

    train, _val, _test = split_dataset(paths)

    assert train


def test_ungrouped_split_is_still_available_for_detection_datasets() -> None:
    """
    Object detection labels a box, not an individual, so a per-image split is
    acceptable there and must remain reachable.
    """
    random.seed(11)
    paths = make_paths({f"clip{i:02d}": 4 for i in range(10)})

    train, val, test = split_dataset(paths, group_by_identity=False)

    assert len(train) + len(val) + len(test) == len(paths)


def test_split_handles_empty_input() -> None:
    assert split_dataset([]) == ([], [], [])


def test_split_ratios_are_approximately_respected() -> None:
    random.seed(21)
    paths = make_paths({f"clip{i:03d}": 1 for i in range(100)})

    train, val, test = split_dataset(paths, train_ratio=0.7, val_ratio=0.15)

    # One group per file here, so group ratios equal file ratios.
    assert len(train) == pytest.approx(70, abs=2)
    assert len(val) == pytest.approx(15, abs=2)
    assert len(test) == pytest.approx(15, abs=2)
