"""
FishEncoder architecture and preprocessing.

Two distinct risks are covered here.

**Shape correctness.** Every block in the encoder transforms a tensor; a wrong
channel count or stride surfaces as a runtime error deep inside a training run, or
worse, as silently degraded embeddings. Small random tensors are cheap and pin the
contract of each block.

**Train/inference preprocessing parity.** This is the highest-consequence class of
bug in a re-identification system. Embeddings are only comparable if they were
produced by the same transform, and nothing about a mismatch raises — matching
accuracy simply collapses. The audit found the offline research script diverging
from the service here (it omitted the fingerprint crop entirely), so the transform
composition and the parameters that identify it are asserted explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch is required for encoder tests")

from PIL import Image  # noqa: E402

from app.services.fish_encoder_model import (  # noqa: E402
    AddCoords,
    CoordConv2d,
    DropBlock2D,
    FishFingerprintCrop,
    GeM,
    GlobalContext,
    MixStyle,
    build_eval_transform,
)


def rand_feature_map(batch: int = 2, channels: int = 8, height: int = 16, width: int = 16):
    """Build a random feature map with a deterministic seed."""
    torch.manual_seed(0)
    return torch.randn(batch, channels, height, width)


def make_roi(width: int = 400, height: int = 120) -> Image.Image:
    """Build a synthetic deskewed fish ROI as a PIL image."""
    array = np.zeros((height, width, 3), dtype=np.uint8)
    # A horizontal gradient makes crop boundaries verifiable.
    array[:, :, 0] = np.linspace(0, 255, width, dtype=np.uint8)
    return Image.fromarray(array)


# ─────────────────────────────────────────────────────────────────────────────
# GeM pooling
# ─────────────────────────────────────────────────────────────────────────────
def test_gem_pools_spatial_dimensions_to_one() -> None:
    layer = GeM(in_dim=8)

    output = layer(rand_feature_map(channels=8).abs())

    assert output.shape == (2, 8, 1, 1)


def test_gem_learns_one_exponent_per_channel() -> None:
    layer = GeM(in_dim=16)

    assert layer.p.shape == (16,)


def test_gem_with_p_one_approximates_average_pooling() -> None:
    """p=1 is the mathematical definition of mean pooling; a drift here changes
    every embedding."""
    layer = GeM(in_dim=4, p=1.0)
    x = rand_feature_map(channels=4).abs() + 0.1

    pooled = layer(x).flatten()
    expected = x.mean(dim=(2, 3)).flatten()

    torch.testing.assert_close(pooled, expected, rtol=1e-4, atol=1e-4)


def test_gem_exponent_is_clamped_into_range() -> None:
    """Training must not drive the exponent into a degenerate regime."""
    layer = GeM(in_dim=4, p=100.0)

    output = layer(rand_feature_map(channels=4).abs() + 0.1)

    assert torch.isfinite(output).all()


# ─────────────────────────────────────────────────────────────────────────────
# MixStyle
# ─────────────────────────────────────────────────────────────────────────────
def test_mixstyle_is_identity_at_eval_time() -> None:
    """
    A train-time augmentation that leaked into inference would perturb embeddings
    non-deterministically, so two captures of the same fish would not match.
    """
    layer = MixStyle(p=1.0).eval()
    x = rand_feature_map()

    torch.testing.assert_close(layer(x), x)


def test_mixstyle_preserves_shape_in_training_mode() -> None:
    layer = MixStyle(p=1.0).train()
    x = rand_feature_map()

    assert layer(x).shape == x.shape


def test_mixstyle_with_probability_zero_is_identity_even_in_training() -> None:
    layer = MixStyle(p=0.0).train()
    x = rand_feature_map()

    torch.testing.assert_close(layer(x), x)


# ─────────────────────────────────────────────────────────────────────────────
# DropBlock
# ─────────────────────────────────────────────────────────────────────────────
def test_dropblock_is_identity_at_eval_time() -> None:
    layer = DropBlock2D(drop_prob=0.5).eval()
    x = rand_feature_map()

    torch.testing.assert_close(layer(x), x)


def test_dropblock_with_zero_probability_is_identity() -> None:
    layer = DropBlock2D(drop_prob=0.0).train()
    x = rand_feature_map()

    torch.testing.assert_close(layer(x), x)


def test_dropblock_preserves_shape_when_active() -> None:
    layer = DropBlock2D(drop_prob=0.3, block_size=3).train()
    x = rand_feature_map()

    assert layer(x).shape == x.shape


# ─────────────────────────────────────────────────────────────────────────────
# Coordinate channels
# ─────────────────────────────────────────────────────────────────────────────
def test_addcoords_appends_two_channels_without_radius() -> None:
    layer = AddCoords(with_r=False)

    output = layer(rand_feature_map(channels=8))

    assert output.shape == (2, 10, 16, 16)


def test_addcoords_appends_three_channels_with_radius() -> None:
    layer = AddCoords(with_r=True)

    output = layer(rand_feature_map(channels=8))

    assert output.shape == (2, 11, 16, 16)


def test_addcoords_preserves_the_original_channels_unchanged() -> None:
    """The coordinate channels must be appended, not overwrite the features."""
    layer = AddCoords(with_r=False)
    x = rand_feature_map(channels=8)

    output = layer(x)

    torch.testing.assert_close(output[:, :8], x)


def test_addcoords_channels_span_the_normalised_range() -> None:
    """
    Absolute position carries signal here: the spot pattern is always sampled
    from the same body region, so the encoder can use where a feature sits.
    """
    layer = AddCoords(with_r=False)

    output = layer(rand_feature_map(channels=4, height=8, width=8))
    coords = output[:, 4:6]

    assert coords.min() >= -1.01
    assert coords.max() <= 1.01


def test_coordconv_maps_to_the_requested_output_channels() -> None:
    layer = CoordConv2d(in_channels=8, out_channels=16, kernel_size=3, padding=1)

    output = layer(rand_feature_map(channels=8))

    assert output.shape == (2, 16, 16, 16)


def test_coordconv_stride_two_halves_the_resolution() -> None:
    layer = CoordConv2d(in_channels=8, out_channels=8, kernel_size=3, stride=2, padding=1)

    output = layer(rand_feature_map(channels=8, height=16, width=16))

    assert output.shape[-2:] == (8, 8)


# ─────────────────────────────────────────────────────────────────────────────
# Global context
# ─────────────────────────────────────────────────────────────────────────────
def test_global_context_preserves_shape() -> None:
    layer = GlobalContext(channels=8)

    x = rand_feature_map(channels=8)

    assert layer(x).shape == x.shape


def test_global_context_rescales_rather_than_zeroing() -> None:
    layer = GlobalContext(channels=8).eval()

    output = layer(rand_feature_map(channels=8))

    assert torch.isfinite(output).all()
    assert output.abs().sum() > 0


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint crop
# ─────────────────────────────────────────────────────────────────────────────
def test_fingerprint_crop_extracts_the_configured_fraction() -> None:
    crop = FishFingerprintCrop(x_start=0.2, x_end=0.8, y_start=0.0, y_end=0.5)

    result = crop(make_roi(width=1000, height=200))

    assert result.size == (600, 100)


def test_fingerprint_crop_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError):
        FishFingerprintCrop(x_start=0.8, x_end=0.2, y_start=0.0, y_end=1.0)


def test_fingerprint_crop_rejects_out_of_range_bounds() -> None:
    with pytest.raises(ValueError):
        FishFingerprintCrop(x_start=-0.1, x_end=0.5, y_start=0.0, y_end=1.0)


def test_fingerprint_crop_full_bounds_is_a_no_op_in_size() -> None:
    crop = FishFingerprintCrop(x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0)
    roi = make_roi(width=320, height=96)

    assert crop(roi).size == roi.size


def test_fingerprint_crop_takes_the_left_dorsal_region() -> None:
    """
    The default bounds target the left dorsal area. Verified through the ROI's
    horizontal gradient: the crop's leftmost column must be brighter than the
    original's, since it starts 20% in.
    """
    crop = FishFingerprintCrop(x_start=0.2, x_end=0.5, y_start=0.0, y_end=0.5)
    roi = make_roi(width=500, height=100)

    cropped = np.asarray(crop(roi))
    original = np.asarray(roi)

    assert cropped[0, 0, 0] > original[0, 0, 0]


def test_fingerprint_crop_repr_shows_its_bounds() -> None:
    crop = FishFingerprintCrop(x_start=0.15, x_end=0.5, y_start=0.05, y_end=0.55)

    text = repr(crop)

    assert "0.15" in text
    assert "0.5" in text


# ─────────────────────────────────────────────────────────────────────────────
# Eval transform — train/inference parity
# ─────────────────────────────────────────────────────────────────────────────
def test_eval_transform_produces_the_configured_square_size() -> None:
    transform = build_eval_transform(img_size=128)

    tensor = transform(make_roi())

    assert tensor.shape == (3, 128, 128)


def test_eval_transform_applies_imagenet_normalisation() -> None:
    """
    The backbone is ImageNet-pretrained, so its statistics must be used. Wrong
    statistics do not raise; they just move every embedding.
    """
    transform = build_eval_transform(img_size=64)

    tensor = transform(make_roi())

    # A [0,1] tensor normalised by these stats leaves this range.
    assert tensor.min() < 0.0
    assert tensor.max() < 2.7


def test_eval_transform_without_fingerprint_has_three_stages() -> None:
    """Resize, ToTensor, Normalize — and nothing else."""
    transform = build_eval_transform(img_size=128, use_fingerprint_crop=False)

    assert len(transform.transforms) == 3


def test_eval_transform_with_fingerprint_prepends_exactly_one_crop() -> None:
    """
    Applying the crop twice would compound the region and silently change what the
    encoder sees, so the count is pinned.
    """
    transform = build_eval_transform(img_size=128, use_fingerprint_crop=True)

    crops = [t for t in transform.transforms if isinstance(t, FishFingerprintCrop)]

    assert len(crops) == 1
    assert isinstance(transform.transforms[0], FishFingerprintCrop)


def test_fingerprint_transform_output_shape_matches_the_plain_one() -> None:
    """
    Both variants must feed the encoder the same shape; only the content differs.
    Otherwise enabling the crop would break the model input contract.
    """
    plain = build_eval_transform(img_size=128, use_fingerprint_crop=False)
    fingerprint = build_eval_transform(img_size=128, use_fingerprint_crop=True)
    roi = make_roi()

    assert plain(roi).shape == fingerprint(roi).shape


def test_fingerprint_transform_changes_the_content() -> None:
    """A crop that produced identical tensors would mean it never ran."""
    plain = build_eval_transform(img_size=64, use_fingerprint_crop=False)
    fingerprint = build_eval_transform(img_size=64, use_fingerprint_crop=True)
    roi = make_roi()

    assert not torch.allclose(plain(roi), fingerprint(roi))


def test_eval_transform_is_deterministic() -> None:
    """
    Inference must contain no randomness: the same ROI has to yield the same
    embedding on every call, or a fish would not match itself.
    """
    transform = build_eval_transform(img_size=64)
    roi = make_roi()

    torch.testing.assert_close(transform(roi), transform(roi))


def test_eval_transform_honours_custom_fingerprint_bounds() -> None:
    """
    The bounds are part of the model_version identity; embeddings built with
    different bounds are not comparable.
    """
    wide = build_eval_transform(
        img_size=64, use_fingerprint_crop=True, x_start=0.0, x_end=1.0
    )
    narrow = build_eval_transform(
        img_size=64, use_fingerprint_crop=True, x_start=0.4, x_end=0.6
    )
    roi = make_roi()

    assert not torch.allclose(wide(roi), narrow(roi))


@pytest.mark.parametrize("size", [64, 128, 224])
def test_eval_transform_supports_the_configured_sizes(size: int) -> None:
    transform = build_eval_transform(img_size=size)

    assert transform(make_roi()).shape == (3, size, size)
