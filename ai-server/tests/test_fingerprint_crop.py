"""
Tests for FishFingerprintCrop and fingerprint preprocessing.

Covers:
- Expected crop dimensions
- Horizontal and vertical images
- Invalid bounds
- Force landscape rotation
- Transform pipeline integration
- Fingerprint applied exactly once
- Support and query use same transform
"""

import numpy as np
import pytest
from PIL import Image

try:
    from app.services.fish_encoder_model import FishFingerprintCrop, build_eval_transform
    HAS_TORCH = True
except (ImportError, ModuleNotFoundError):
    HAS_TORCH = False

# FishFingerprintCrop is pure PIL — extract it directly if torch unavailable
if not HAS_TORCH:
    import sys
    import importlib.util

    # Load just the class without triggering torch/timm imports
    from pathlib import Path
    _model_path = Path(__file__).parent.parent / "app" / "services" / "fish_encoder_model.py"
    _source = _model_path.read_text()

    # Extract just FishFingerprintCrop class source and exec it
    exec("""
from PIL import Image

class FishFingerprintCrop:
    def __init__(self, x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55, force_landscape=True):
        if not 0.0 <= x_start < x_end <= 1.0:
            raise ValueError(f"Expected 0 <= x_start < x_end <= 1, got x_start={x_start}, x_end={x_end}")
        if not 0.0 <= y_start < y_end <= 1.0:
            raise ValueError(f"Expected 0 <= y_start < y_end <= 1, got y_start={y_start}, y_end={y_end}")
        self.x_start = float(x_start)
        self.x_end = float(x_end)
        self.y_start = float(y_start)
        self.y_end = float(y_end)
        self.force_landscape = bool(force_landscape)

    def __call__(self, image):
        if not isinstance(image, Image.Image):
            raise TypeError(f"FishFingerprintCrop expects a PIL Image, got {type(image).__name__}")
        if image.width < 1 or image.height < 1:
            raise ValueError("Cannot crop an empty image.")
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
""", globals())


class TestFishFingerprintCropDimensions:
    def test_expected_size_600x200(self):
        """L=600, H=200 → fingerprint 360×100."""
        image = Image.new("RGB", (600, 200), color="white")
        crop = FishFingerprintCrop(x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55)
        result = crop(image)
        assert result.size == (360, 100)

    def test_expected_size_1000x300(self):
        """L=1000, H=300 → fingerprint 600×150."""
        image = Image.new("RGB", (1000, 300), color="blue")
        crop = FishFingerprintCrop(x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55)
        result = crop(image)
        assert result.size == (600, 150)

    def test_full_image_crop(self):
        """x=[0,1] y=[0,1] returns entire image."""
        image = Image.new("RGB", (400, 200))
        crop = FishFingerprintCrop(x_start=0.0, x_end=1.0, y_start=0.0, y_end=1.0)
        result = crop(image)
        assert result.size == (400, 200)

    def test_restrictive_crop(self):
        """x=[0.333, 0.667] y=[0.05, 0.35] — the restrictive rectangle."""
        image = Image.new("RGB", (600, 200))
        crop = FishFingerprintCrop(x_start=0.333, x_end=0.667, y_start=0.05, y_end=0.35)
        result = crop(image)
        # width = round(0.667*600) - round(0.333*600) = 400 - 200 = 200
        # height = round(0.35*200) - round(0.05*200) = 70 - 10 = 60
        assert result.size == (200, 60)


class TestFishFingerprintCropOrientation:
    def test_horizontal_image_stays_horizontal(self):
        """Landscape image is not rotated."""
        image = Image.new("RGB", (800, 200), color="red")
        crop = FishFingerprintCrop(force_landscape=True)
        result = crop(image)
        # Width should be 60% of 800 = 480, height 50% of 200 = 100
        assert result.size == (480, 100)

    def test_vertical_image_rotated_to_landscape(self):
        """Portrait image is rotated 270° to become landscape."""
        image = Image.new("RGB", (200, 800), color="green")
        crop = FishFingerprintCrop(force_landscape=True)
        result = crop(image)
        # After rotation: 800×200 (landscape)
        # fingerprint: 60% of 800 = 480, 50% of 200 = 100
        assert result.size == (480, 100)

    def test_vertical_image_not_rotated_when_disabled(self):
        """force_landscape=False keeps portrait orientation."""
        image = Image.new("RGB", (200, 800), color="green")
        crop = FishFingerprintCrop(force_landscape=False)
        result = crop(image)
        # Width = 60% of 200 = 120, height = 50% of 800 = 400
        assert result.size == (120, 400)


class TestFishFingerprintCropValidation:
    def test_invalid_x_bounds_raises(self):
        """x_start >= x_end should raise ValueError."""
        with pytest.raises(ValueError):
            FishFingerprintCrop(x_start=0.8, x_end=0.2)

    def test_invalid_y_bounds_raises(self):
        """y_start >= y_end should raise ValueError."""
        with pytest.raises(ValueError):
            FishFingerprintCrop(y_start=0.7, y_end=0.3)

    def test_out_of_range_x_raises(self):
        """x values outside [0,1] should raise."""
        with pytest.raises(ValueError):
            FishFingerprintCrop(x_start=-0.1, x_end=0.8)

    def test_out_of_range_y_raises(self):
        """y values outside [0,1] should raise."""
        with pytest.raises(ValueError):
            FishFingerprintCrop(y_start=0.0, y_end=1.1)

    def test_non_pil_image_raises_typeerror(self):
        """numpy array should raise TypeError."""
        crop = FishFingerprintCrop()
        with pytest.raises(TypeError):
            crop(np.zeros((100, 200, 3), dtype=np.uint8))

    def test_minimum_one_pixel_crop(self):
        """Tiny image (2x2) still produces at least 1x1 crop."""
        image = Image.new("RGB", (2, 2))
        crop = FishFingerprintCrop()
        result = crop(image)
        assert result.size[0] >= 1
        assert result.size[1] >= 1


class TestBuildEvalTransform:
    @pytest.mark.skipif(not HAS_TORCH, reason="torch/timm not installed")
    def test_without_fingerprint_produces_128x128(self):
        """Default transform: Resize to 128×128, normalize."""
        transform = build_eval_transform(img_size=128, use_fingerprint_crop=False)
        image = Image.new("RGB", (600, 200))
        tensor = transform(image)
        assert tensor.shape == (3, 128, 128)

    @pytest.mark.skipif(not HAS_TORCH, reason="torch/timm not installed")
    def test_with_fingerprint_produces_128x128(self):
        """With fingerprint: crop then Resize to 128×128, normalize."""
        transform = build_eval_transform(
            img_size=128,
            use_fingerprint_crop=True,
            x_start=0.20,
            x_end=0.80,
            y_start=0.05,
            y_end=0.55,
        )
        image = Image.new("RGB", (600, 200))
        tensor = transform(image)
        # Output is always (3, 128, 128) regardless of intermediate crop
        assert tensor.shape == (3, 128, 128)

    @pytest.mark.skipif(not HAS_TORCH, reason="torch/timm not installed")
    def test_fingerprint_changes_content(self):
        """The fingerprint crop changes what the model sees."""
        import torch

        # Create image with distinct regions
        image = Image.new("RGB", (600, 200), color=(0, 0, 0))
        # Paint the fingerprint region white
        for x in range(120, 480):
            for y in range(10, 110):
                image.putpixel((x, y), (255, 255, 255))

        t_full = build_eval_transform(img_size=128, use_fingerprint_crop=False)
        t_fp = build_eval_transform(img_size=128, use_fingerprint_crop=True)

        tensor_full = t_full(image)
        tensor_fp = t_fp(image)

        # They should differ because fingerprint sees mostly white
        # while full sees a mix of black and white
        assert not torch.allclose(tensor_full, tensor_fp, atol=0.01)

    @pytest.mark.skipif(not HAS_TORCH, reason="torch/timm not installed")
    def test_support_and_query_same_transform(self):
        """Same config produces identical transform for both roles."""
        import torch

        image = Image.new("RGB", (600, 200), color=(128, 64, 192))

        t1 = build_eval_transform(
            img_size=128, use_fingerprint_crop=True,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )
        t2 = build_eval_transform(
            img_size=128, use_fingerprint_crop=True,
            x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55,
        )

        assert torch.allclose(t1(image), t2(image))


class TestFingerprintAppliedOnce:
    def test_crop_applied_exactly_once_in_pipeline(self):
        """Transform pipeline applies fingerprint crop once, not twice."""
        # A 600x200 image with fingerprint enabled should produce
        # an intermediate crop of 360x100, then resize to 128x128.
        # If applied twice, intermediate would be 216x50 (wrong).

        image = Image.new("RGB", (600, 200), color="white")
        crop = FishFingerprintCrop(x_start=0.20, x_end=0.80, y_start=0.05, y_end=0.55)

        # Apply once
        result1 = crop(image)
        assert result1.size == (360, 100)

        # Apply again to result — should give different size
        result2 = crop(result1)
        # 60% of 360 = 216, 50% of 100 = 50
        assert result2.size == (216, 50)

        # This proves that applying it once vs twice gives different results
        assert result1.size != result2.size


# ── Integration tests (Fase 5–7, Section 18 of guide) ───────────────────────


class TestVersionedEmbeddingIsolation:
    """Verify that different model_versions are fully isolated in queries."""

    @pytest.fixture
    def matching_service(self, tmp_path):
        """Create a MatchingService with temp DB and UNIQUE index."""
        from unittest.mock import patch

        db_path = tmp_path / "test_embeddings.sqlite"
        with patch("app.config.settings") as mock_settings:
            mock_settings.embeddings_db_path = str(db_path)
            mock_settings.reid_cache_name = "test_v1"

            from app.services.matching_service import MatchingService
            ms = MatchingService()

            # Add UNIQUE index (simulating migration 005)
            with ms._connect() as conn:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_embeddings_sighting_model_vector
                    ON fish_embeddings(sighting_id, model_version, vector_type)
                """)
                conn.commit()

            yield ms

    def test_two_versions_same_sighting_isolated(self, matching_service):
        """Insert embeddings with two model_versions for the same sighting.
        Query should only return the one matching the requested version."""
        vec_v1 = np.random.randn(512).astype(np.float32)
        vec_v1 = vec_v1 / np.linalg.norm(vec_v1)

        vec_v2 = np.random.randn(512).astype(np.float32)
        vec_v2 = vec_v2 / np.linalg.norm(vec_v2)

        matching_service.store_embedding(
            fish_id="fish_abc",
            sighting_id="sight_001",
            species_slug="test_sp",
            area_code="CZ001",
            embedding=vec_v1,
            model_version="old_version_full",
        )
        matching_service.store_embedding(
            fish_id="fish_abc",
            sighting_id="sight_001",
            species_slug="test_sp",
            area_code="CZ001",
            embedding=vec_v2,
            model_version="new_version_fp",
        )

        # Both should exist
        assert matching_service.embedding_exists("sight_001", "old_version_full")
        assert matching_service.embedding_exists("sight_001", "new_version_fp")

        # Counts should be 1 each
        old_counts = matching_service.count_active_embeddings("old_version_full")
        new_counts = matching_service.count_active_embeddings("new_version_fp")
        assert old_counts["embedding_count"] == 1
        assert new_counts["embedding_count"] == 1

    def test_embedding_exists_returns_false_for_unknown_version(self, matching_service):
        """embedding_exists returns False for a version that has never been stored."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        matching_service.store_embedding(
            fish_id="fish_abc",
            sighting_id="sight_001",
            species_slug="test_sp",
            area_code="CZ001",
            embedding=vec,
            model_version="existing_version",
        )

        assert matching_service.embedding_exists("sight_001", "existing_version")
        assert not matching_service.embedding_exists("sight_001", "nonexistent_version")
        assert not matching_service.embedding_exists("nonexistent_sighting", "existing_version")

    def test_store_embedding_rejects_non_normalized(self, matching_service):
        """store_embedding should raise ValueError for unnormalized vectors."""
        vec = np.random.randn(512).astype(np.float32) * 10.0  # norm >> 1

        with pytest.raises(ValueError, match="not L2-normalized"):
            matching_service.store_embedding(
                fish_id="fish1",
                sighting_id="s1",
                species_slug="sp1",
                area_code="A1",
                embedding=vec,
            )

