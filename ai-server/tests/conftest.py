"""
Shared pytest configuration.

Guarantees test isolation for the two pieces of global state that would
otherwise leak between tests: the settings singleton (driven by environment
variables) and the identification result cache.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Force a deterministic, non-production configuration before app.config is
# imported by any test module. Without this, a developer's local .env could flip
# the suite into production mode and change authorisation behaviour.
os.environ.setdefault("FISHDEX_ENVIRONMENT", "test")
os.environ.setdefault("FISHDEX_SKIP_AUTH", "false")
os.environ.setdefault("FISHDEX_AI_SERVER_SECRET", "test-server-secret-not-a-placeholder")
os.environ.setdefault("FISHDEX_CLIENT_SECRET", "test-client-secret-not-a-placeholder")
os.environ.setdefault("FISHDEX_DASHBOARD_SECRET", "test-dashboard-secret")


@pytest.fixture(autouse=True)
def _clear_result_cache() -> Iterator[None]:
    """
    Empty the identification result cache around every test.

    The cache is a process-wide singleton; without this a cached document from
    one test would satisfy a lookup in the next.
    """
    from app.services.result_cache import get_result_cache

    get_result_cache().clear()
    yield
    get_result_cache().clear()


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point every configured storage directory at a temporary location.

    Args:
        tmp_path: pytest-provided scratch directory.
        monkeypatch: pytest patcher.

    Returns:
        The root of the isolated data directory.
    """
    from app.config import settings

    root = tmp_path / "data"
    for attribute, relative in (
        ("server_data_dir", "."),
        ("temp_dir", "temp"),
        ("cache_dir", "cache"),
        ("private_data_dir", "private"),
        ("fish_documents_dir", "private/fish_documents"),
        ("fish_media_dir", "storage/fish_media"),
        ("job_artifacts_dir", "storage/jobs"),
    ):
        path = (root / relative).resolve()
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(settings, attribute, str(path), raising=False)

    embeddings = root / "embeddings" / "fishdex_embeddings.sqlite"
    embeddings.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "embeddings_db_path", str(embeddings), raising=False)

    return root


@pytest.fixture
def blank_frame():
    """A 640x480 uniform BGR frame, useful for geometry assertions."""
    import numpy as np

    return np.full((480, 640, 3), 120, dtype=np.uint8)
