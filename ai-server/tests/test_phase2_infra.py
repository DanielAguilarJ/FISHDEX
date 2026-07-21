"""
Tests for Phase 2: Migrations, model fingerprint, audit commands, and health endpoints.
"""

import sqlite3
import json
import pytest
from pathlib import Path
from unittest.mock import patch


class TestMigrationSystem:
    """Tests for the versioned migration runner."""

    def test_run_migrations_creates_schema_table(self, tmp_path, monkeypatch):
        """Migrations create schema_migrations tracking table."""
        db_path = tmp_path / "test.sqlite"
        monkeypatch.setattr("app.config.settings.embeddings_db_path", str(tmp_path / "emb.sqlite"))
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Create base tables that migrations expect to exist
        conn.execute("CREATE TABLE identification_jobs (id TEXT PRIMARY KEY, user_id TEXT, status TEXT)")
        conn.commit()
        
        from app.migrations.runner import run_migrations, get_current_version
        
        version = run_migrations(conn)
        assert version >= 1
        
        current = get_current_version(conn)
        assert current == version
        conn.close()

    def test_migrations_are_idempotent(self, tmp_path, monkeypatch):
        """Running migrations twice produces the same result."""
        db_path = tmp_path / "test.sqlite"
        monkeypatch.setattr("app.config.settings.embeddings_db_path", str(tmp_path / "emb.sqlite"))
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE identification_jobs (id TEXT PRIMARY KEY, user_id TEXT, status TEXT)")
        conn.commit()
        
        from app.migrations.runner import run_migrations
        
        v1 = run_migrations(conn)
        v2 = run_migrations(conn)
        assert v1 == v2
        conn.close()

    def test_migration_001_adds_decision_fields(self, tmp_path, monkeypatch):
        """Migration 001 adds decision-related columns to identification_jobs."""
        db_path = tmp_path / "test.sqlite"
        monkeypatch.setattr("app.config.settings.embeddings_db_path", str(tmp_path / "emb.sqlite"))
        
        conn = sqlite3.connect(str(db_path))
        # Create the base table first
        conn.execute("""
            CREATE TABLE identification_jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        conn.commit()
        
        import importlib
        m001 = importlib.import_module("app.migrations.versions.001_add_decision_fields")
        m001.up(conn)
        
        # Check that decision column exists
        cursor = conn.execute("PRAGMA table_info(identification_jobs)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "decision" in cols
        assert "proposed_fish_id" in cols
        assert "top1_score" in cols
        assert "match_margin" in cols
        assert "model_version" in cols
        assert "gps_accuracy_m" in cols
        assert "review_case_id" in cols
        conn.close()

    def test_migration_002_creates_review_cases(self, tmp_path, monkeypatch):
        """Migration 002 creates the identification_review_cases table."""
        db_path = tmp_path / "test.sqlite"
        monkeypatch.setattr("app.config.settings.embeddings_db_path", str(tmp_path / "emb.sqlite"))
        
        conn = sqlite3.connect(str(db_path))
        
        import importlib
        m002 = importlib.import_module("app.migrations.versions.002_create_review_cases")
        m002.up(conn)
        
        # Verify table exists and has correct structure
        cursor = conn.execute("PRAGMA table_info(identification_review_cases)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "id" in cols
        assert "job_id" in cols
        assert "proposed_fish_id" in cols
        assert "state" in cols
        assert "reason_codes_json" in cols
        assert "metrics_json" in cols
        assert "reviewed_by" in cols
        assert "resolution" in cols
        conn.close()


class TestModelFingerprint:
    """Tests for model fingerprint service."""

    def test_compute_sha256_of_file(self, tmp_path):
        """SHA-256 computation works on a real file."""
        from app.services.model_fingerprint_service import compute_checkpoint_sha256
        
        # Create a dummy file
        test_file = tmp_path / "model.pt"
        test_file.write_bytes(b"fake model weights for testing" * 100)
        
        sha = compute_checkpoint_sha256(test_file)
        assert len(sha) == 12  # First 12 hex chars
        assert sha.isalnum()

    def test_missing_checkpoint_raises(self, tmp_path):
        """ModelNotAvailableError when checkpoint doesn't exist."""
        from app.services.model_fingerprint_service import (
            compute_checkpoint_sha256,
            ModelNotAvailableError,
        )
        
        with pytest.raises((ModelNotAvailableError, FileNotFoundError)):
            compute_checkpoint_sha256(tmp_path / "nonexistent.pt")

    def test_fingerprint_version_format(self, tmp_path, monkeypatch):
        """Model version string follows expected format."""
        from app.services import model_fingerprint_service as mfp
        
        # Reset singleton
        mfp._fingerprint_cache = None
        
        # Create a fake checkpoint
        checkpoint = tmp_path / "reid_best.pt"
        checkpoint.write_bytes(b"x" * 1000)
        
        monkeypatch.setattr("app.config.settings.reid_model_path", str(checkpoint))
        monkeypatch.setattr("app.config.settings.reid_model_name", "convnext_small.fb_in22k_ft_in1k")
        monkeypatch.setattr("app.config.settings.reid_embedding_dim", 512)
        monkeypatch.setattr("app.config.settings.reid_img_size", 128)
        monkeypatch.setattr("app.config.settings.reid_flip_tta", True)
        
        fp = mfp.get_model_fingerprint()
        
        assert fp.embedding_dim == 512
        assert fp.image_size == 128
        assert "fishencoder" in fp.model_version
        assert "convnext" in fp.model_version.lower()
        assert "512" in fp.model_version
        
        # Reset
        mfp._fingerprint_cache = None


class TestAuditEmbeddings:
    """Tests for the audit command."""

    def test_audit_runs_on_empty_db(self, tmp_path, monkeypatch):
        """Audit produces a valid report even with empty databases."""
        main_db = tmp_path / "fishdex_local.sqlite"
        emb_db = tmp_path / "embeddings.sqlite"
        
        # Create minimal main DB
        conn = sqlite3.connect(str(main_db))
        conn.execute("CREATE TABLE fish_sightings (id TEXT PRIMARY KEY, fish_id TEXT)")
        conn.execute("CREATE TABLE fish_individuals (id TEXT PRIMARY KEY, fish_id TEXT UNIQUE)")
        conn.commit()
        conn.close()
        
        # Create minimal embeddings DB
        conn = sqlite3.connect(str(emb_db))
        conn.execute("""CREATE TABLE fish_embeddings (
            id TEXT PRIMARY KEY, fish_id TEXT, species_slug TEXT,
            model_version TEXT, embedding BLOB, latitude REAL, longitude REAL
        )""")
        conn.commit()
        conn.close()
        
        monkeypatch.setattr("app.config.settings.server_data_dir", str(tmp_path))
        monkeypatch.setattr("app.config.settings.embeddings_db_path", str(emb_db))
        monkeypatch.setattr("app.database.DB_PATH", main_db)
        
        from app.commands.audit_embeddings import run_audit
        report = run_audit()
        
        assert report["total_sightings"] == 0
        assert report["total_embeddings"] == 0
        assert report["orphan_embeddings_count"] == 0


class TestHealthEndpoints:
    """Tests for /health/live and /health/ready."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app."""
        pytest.importorskip("slowapi")
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_health_live_always_responds(self, client):
        """Liveness probe always returns 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["alive"] is True

    def test_health_ready_returns_structure(self, client):
        """Readiness probe returns expected fields."""
        response = client.get("/health/ready")
        data = response.json()
        
        # Should have these keys regardless of status
        assert "ready" in data
        assert "db_accessible" in data
        assert "match_radius_km" in data
        assert data["match_radius_km"] == 5.0

    def test_health_legacy_still_works(self, client):
        """Legacy /health endpoint still responds."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
