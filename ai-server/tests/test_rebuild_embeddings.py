"""
Tests for rebuild_embeddings command.

Covers:
- _find_crop_files(): strict pattern matching (only images/crop_*.jpg)
- ReIDPreprocessingSpec: fingerprint consistency validation
- Idempotency: INSERT OR IGNORE does not duplicate
- Vector validation in store_embedding
- Embedding version isolation
- embedding_exists() correctness
- Migration version check
"""

import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Test _find_crop_files ────────────────────────────────────────────────────


class TestFindCropFiles:
    """Test that _find_crop_files only returns images/crop_*.jpg."""

    @pytest.fixture
    def artifact_tree(self, tmp_path: Path):
        """Create a realistic artifact directory tree."""
        storage = tmp_path / "storage"

        # The artifact path (relative)
        art_rel = "fish_media/area1/species1/fish001/catch_1_job123"
        art_abs = storage / art_rel

        # Primary OBB crops — SHOULD be found
        images_dir = art_abs / "images"
        images_dir.mkdir(parents=True)
        (images_dir / "crop_00.jpg").write_bytes(self._make_jpeg())
        (images_dir / "crop_01.jpg").write_bytes(self._make_jpeg())

        # Files that should NOT be found:
        (art_abs / "preview.jpg").write_bytes(self._make_jpeg())

        images_bbox = art_abs / "images_bbox"
        images_bbox.mkdir()
        (images_bbox / "crop_00.jpg").write_bytes(self._make_jpeg())

        frames_dir = art_abs / "frames"
        frames_dir.mkdir()
        (frames_dir / "frame_00.jpg").write_bytes(self._make_jpeg())

        dataset_dir = art_abs / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "crop_001_aligned.jpg").write_bytes(self._make_jpeg())

        annotated_dir = art_abs / "annotated"
        annotated_dir.mkdir()
        (annotated_dir / "frame_000.jpg").write_bytes(self._make_jpeg())

        raw_dir = art_abs / "raw"
        raw_dir.mkdir()
        (raw_dir / "video.mp4").write_bytes(b"fake video")

        return tmp_path, art_rel

    @staticmethod
    def _make_jpeg() -> bytes:
        """Create a minimal valid JPEG in memory."""
        import io
        try:
            import cv2
            img = np.zeros((10, 20, 3), dtype=np.uint8)
            _, buf = cv2.imencode(".jpg", img)
            return buf.tobytes()
        except ImportError:
            # Fallback: minimal JPEG header
            return b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"\xff\xd9"

    def test_finds_only_images_dir_crops(self, artifact_tree):
        """Only images/crop_*.jpg should be returned."""
        tmp_path, art_rel = artifact_tree

        with patch("app.config.settings") as mock_settings:
            mock_settings.server_data_dir = str(tmp_path)

            from app.commands.rebuild_embeddings import _find_crop_files
            crops = _find_crop_files(art_rel)

        # Should find exactly 2 crops in images/
        filenames = [p.name for p in crops]
        assert "crop_00.jpg" in filenames
        assert "crop_01.jpg" in filenames
        assert len(crops) == 2

    def test_excludes_preview(self, artifact_tree):
        """preview.jpg should never be included."""
        tmp_path, art_rel = artifact_tree

        with patch("app.config.settings") as mock_settings:
            mock_settings.server_data_dir = str(tmp_path)

            from app.commands.rebuild_embeddings import _find_crop_files
            crops = _find_crop_files(art_rel)

        for p in crops:
            assert "preview" not in p.name

    def test_excludes_images_bbox(self, artifact_tree):
        """images_bbox/ directory crops should not be included."""
        tmp_path, art_rel = artifact_tree

        with patch("app.config.settings") as mock_settings:
            mock_settings.server_data_dir = str(tmp_path)

            from app.commands.rebuild_embeddings import _find_crop_files
            crops = _find_crop_files(art_rel)

        for p in crops:
            assert "images_bbox" not in str(p)

    def test_excludes_dataset(self, artifact_tree):
        """dataset/ directory should not be included."""
        tmp_path, art_rel = artifact_tree

        with patch("app.config.settings") as mock_settings:
            mock_settings.server_data_dir = str(tmp_path)

            from app.commands.rebuild_embeddings import _find_crop_files
            crops = _find_crop_files(art_rel)

        for p in crops:
            assert "dataset" not in str(p)

    def test_empty_artifact_dir_returns_empty(self):
        """None or empty artifact_dir returns []."""
        from app.commands.rebuild_embeddings import _find_crop_files
        assert _find_crop_files(None) == []
        assert _find_crop_files("") == []

    def test_missing_images_dir_returns_empty(self, tmp_path):
        """If images/ doesn't exist, return []."""
        art_rel = "nonexistent/artifact"
        with patch("app.config.settings") as mock_settings:
            mock_settings.server_data_dir = str(tmp_path)

            from app.commands.rebuild_embeddings import _find_crop_files
            assert _find_crop_files(art_rel) == []


# ── Test ReIDPreprocessingSpec ───────────────────────────────────────────────


class TestReIDPreprocessingSpec:
    """Test the immutable preprocessing spec validation."""

    def test_fingerprint_enabled_but_version_has_no_fp_raises(self):
        """model_version without _fp_ but fingerprint enabled should raise."""
        from app.services.reid_preprocessing_spec import ReIDPreprocessingSpec

        spec = ReIDPreprocessingSpec(
            model_version="fishencoder_abc123_convnext-small_512_128_flip1_full",
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            img_size=128,
            flip_tta=True,
            fingerprint_enabled=True,  # ENABLED
            x_start=0.20,
            x_end=0.80,
            y_start=0.05,
            y_end=0.55,
        )

        with pytest.raises(RuntimeError, match="Fingerprint is ENABLED"):
            spec.validate_fingerprint_consistency()

    def test_fingerprint_disabled_but_version_has_fp_raises(self):
        """model_version with _fp_ but fingerprint disabled should raise."""
        from app.services.reid_preprocessing_spec import ReIDPreprocessingSpec

        spec = ReIDPreprocessingSpec(
            model_version="fishencoder_abc123_convnext-small_512_128_flip1_fp_x020_080_y005_055",
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            img_size=128,
            flip_tta=True,
            fingerprint_enabled=False,  # DISABLED
            x_start=0.0,
            x_end=1.0,
            y_start=0.0,
            y_end=1.0,
        )

        with pytest.raises(RuntimeError, match="Fingerprint is DISABLED"):
            spec.validate_fingerprint_consistency()

    def test_consistent_spec_does_not_raise(self):
        """Matching fingerprint state and version should pass."""
        from app.services.reid_preprocessing_spec import ReIDPreprocessingSpec

        # Fingerprint enabled + _fp_ in version
        spec_fp = ReIDPreprocessingSpec(
            model_version="fishencoder_abc123_convnext-small_512_128_flip1_fp_x020_080_y005_055",
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            img_size=128,
            flip_tta=True,
            fingerprint_enabled=True,
            x_start=0.20,
            x_end=0.80,
            y_start=0.05,
            y_end=0.55,
        )
        spec_fp.validate_fingerprint_consistency()  # should not raise

        # Fingerprint disabled + "full" in version
        spec_full = ReIDPreprocessingSpec(
            model_version="fishencoder_abc123_convnext-small_512_128_flip1_full",
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            img_size=128,
            flip_tta=True,
            fingerprint_enabled=False,
            x_start=0.0,
            x_end=1.0,
            y_start=0.0,
            y_end=1.0,
        )
        spec_full.validate_fingerprint_consistency()  # should not raise

    def test_to_dict_round_trips(self):
        """to_dict() preserves all fields."""
        from app.services.reid_preprocessing_spec import ReIDPreprocessingSpec

        spec = ReIDPreprocessingSpec(
            model_version="test_v1",
            checkpoint_sha256="abc",
            model_name="model",
            embedding_dim=512,
            img_size=128,
            flip_tta=True,
            fingerprint_enabled=True,
            x_start=0.2,
            x_end=0.8,
            y_start=0.05,
            y_end=0.55,
        )
        d = spec.to_dict()
        assert d["model_version"] == "test_v1"
        assert d["fingerprint_enabled"] is True
        assert d["x_start"] == 0.2


# ── Test store_embedding vector validation ───────────────────────────────────


class TestStoreEmbeddingValidation:
    """Test that store_embedding validates vectors before storage."""

    @pytest.fixture
    def matching_service(self, tmp_path):
        """Create a MatchingService with temp DB."""
        db_path = tmp_path / "test_embeddings.sqlite"

        with patch("app.config.settings") as mock_settings:
            mock_settings.embeddings_db_path = str(db_path)
            mock_settings.reid_cache_name = "test_v1"

            from app.services.matching_service import MatchingService
            ms = MatchingService()

            # Apply the UNIQUE index
            with ms._connect() as conn:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_embeddings_sighting_model_vector
                    ON fish_embeddings(sighting_id, model_version, vector_type)
                """)
                conn.commit()

            yield ms

    def test_wrong_dimension_raises(self, matching_service):
        """Embedding with wrong dimensions should raise ValueError."""
        vec = np.random.randn(256).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        with pytest.raises(ValueError, match="Expected embedding with 512"):
            matching_service.store_embedding(
                fish_id="fish1",
                sighting_id="s1",
                species_slug="test_species",
                area_code="A1",
                embedding=vec,
                dimensions=512,
            )

    def test_non_finite_raises(self, matching_service):
        """Embedding with NaN should raise ValueError."""
        vec = np.ones(512, dtype=np.float32)
        vec[100] = np.nan

        with pytest.raises(ValueError, match="non-finite"):
            matching_service.store_embedding(
                fish_id="fish1",
                sighting_id="s1",
                species_slug="test_species",
                area_code="A1",
                embedding=vec,
            )

    def test_unnormalized_raises(self, matching_service):
        """Embedding with norm far from 1.0 should raise ValueError."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec * 5.0  # norm >> 1

        with pytest.raises(ValueError, match="not L2-normalized"):
            matching_service.store_embedding(
                fish_id="fish1",
                sighting_id="s1",
                species_slug="test_species",
                area_code="A1",
                embedding=vec,
            )

    def test_valid_embedding_stores_ok(self, matching_service):
        """Properly normalized 512-d embedding should store successfully."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        matching_service.store_embedding(
            fish_id="fish1",
            sighting_id="s1",
            species_slug="test_species",
            area_code="A1",
            embedding=vec,
            model_version="test_v1",
        )

        assert matching_service.embedding_exists("s1", "test_v1")


# ── Test idempotency with UNIQUE index ───────────────────────────────────────


class TestEmbeddingIdempotency:
    """Test INSERT OR IGNORE idempotency."""

    @pytest.fixture
    def matching_service(self, tmp_path):
        db_path = tmp_path / "test_embeddings.sqlite"

        with patch("app.config.settings") as mock_settings:
            mock_settings.embeddings_db_path = str(db_path)
            mock_settings.reid_cache_name = "test_v1"

            from app.services.matching_service import MatchingService
            ms = MatchingService()

            with ms._connect() as conn:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_embeddings_sighting_model_vector
                    ON fish_embeddings(sighting_id, model_version, vector_type)
                """)
                conn.commit()

            yield ms

    def test_double_insert_does_not_duplicate(self, matching_service):
        """Inserting same (sighting_id, model_version, vector_type) twice
        should result in only one row."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        matching_service.store_embedding(
            fish_id="fish1",
            sighting_id="s1",
            species_slug="sp1",
            area_code="A1",
            embedding=vec,
            model_version="test_v1",
        )
        matching_service.store_embedding(
            fish_id="fish1",
            sighting_id="s1",
            species_slug="sp1",
            area_code="A1",
            embedding=vec,
            model_version="test_v1",
        )

        with matching_service._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fish_embeddings "
                "WHERE sighting_id = 'id1' OR sighting_id = 's1'"
            ).fetchone()[0]

        # Should be exactly 1 row
        assert count == 1

    def test_different_model_version_creates_separate_row(self, matching_service):
        """Different model_version for same sighting creates a new row."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        matching_service.store_embedding(
            fish_id="fish1", sighting_id="s1",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v1",
        )
        matching_service.store_embedding(
            fish_id="fish1", sighting_id="s1",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v2",
        )

        with matching_service._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM fish_embeddings WHERE sighting_id = 's1'"
            ).fetchone()[0]

        assert count == 2


# ── Test version isolation ───────────────────────────────────────────────────


class TestVersionIsolation:
    """Test that queries filter by model_version correctly."""

    @pytest.fixture
    def matching_service(self, tmp_path):
        db_path = tmp_path / "test_embeddings.sqlite"

        with patch("app.config.settings") as mock_settings:
            mock_settings.embeddings_db_path = str(db_path)
            mock_settings.reid_cache_name = "test_v1"

            from app.services.matching_service import MatchingService
            ms = MatchingService()

            with ms._connect() as conn:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_embeddings_sighting_model_vector
                    ON fish_embeddings(sighting_id, model_version, vector_type)
                """)
                conn.commit()

            yield ms

    def test_embedding_exists_filters_by_version(self, matching_service):
        """embedding_exists returns True only for the queried version."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        matching_service.store_embedding(
            fish_id="fish1", sighting_id="s1",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v_old",
        )

        assert matching_service.embedding_exists("s1", "v_old")
        assert not matching_service.embedding_exists("s1", "v_new")

    def test_count_active_embeddings_filters(self, matching_service):
        """count_active_embeddings only counts the specified version."""
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)

        # Insert 2 embeddings with v_old
        matching_service.store_embedding(
            fish_id="fish1", sighting_id="s1",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v_old",
        )
        matching_service.store_embedding(
            fish_id="fish2", sighting_id="s2",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v_old",
        )

        # Insert 1 with v_new
        matching_service.store_embedding(
            fish_id="fish1", sighting_id="s1",
            species_slug="sp1", area_code="A1",
            embedding=vec, model_version="v_new",
        )

        counts_old = matching_service.count_active_embeddings("v_old")
        counts_new = matching_service.count_active_embeddings("v_new")

        assert counts_old["embedding_count"] == 2
        assert counts_old["fish_count"] == 2
        assert counts_new["embedding_count"] == 1
        assert counts_new["fish_count"] == 1


# ── Test ModelFingerprint version format ─────────────────────────────────────


class TestModelFingerprintVersionFormat:
    """Test that model_version is Windows-safe and encodes fingerprint coords."""

    def test_version_uses_underscores_not_colons(self):
        """model_version should use _ not : (Windows-safe)."""
        from app.services.model_fingerprint_service import ModelFingerprint

        fp = ModelFingerprint(
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            image_size=128,
            preprocessing_version="prep1",
            tta_version="flip1",
            crop_version="full",
            normalization_version="l2_v1",
        )

        assert ":" not in fp.model_version
        assert "_" in fp.model_version
        assert fp.model_version.startswith("fishencoder_")

    def test_fingerprint_version_encodes_coords(self):
        """With fingerprint enabled, version includes fp_xNNN_NNN_yNNN_NNN."""
        from app.services.model_fingerprint_service import ModelFingerprint

        fp = ModelFingerprint(
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            image_size=128,
            preprocessing_version="prep1",
            tta_version="flip1",
            crop_version="fp_x020_080_y005_055",
            normalization_version="l2_v1",
            fingerprint_enabled=True,
            fingerprint_x_start=0.20,
            fingerprint_x_end=0.80,
            fingerprint_y_start=0.05,
            fingerprint_y_end=0.55,
        )

        assert "fp_x020_080_y005_055" in fp.model_version
        assert fp.fingerprint_crop_version == "fp_x020_080_y005_055"

    def test_no_fingerprint_shows_full(self):
        """Without fingerprint, version includes 'full'."""
        from app.services.model_fingerprint_service import ModelFingerprint

        fp = ModelFingerprint(
            checkpoint_sha256="abc123def456",
            model_name="convnext_small.fb_in22k_ft_in1k",
            embedding_dim=512,
            image_size=128,
            preprocessing_version="prep1",
            tta_version="flip1",
            crop_version="full",
            normalization_version="l2_v1",
            fingerprint_enabled=False,
        )

        assert "_full" in fp.model_version
        assert fp.fingerprint_crop_version == "full"
