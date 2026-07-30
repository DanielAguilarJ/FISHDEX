"""
API integration tests.

These exercise the real FastAPI application through ``TestClient`` — no running
server and no network required. The previous version of this file issued
``httpx`` calls to ``http://127.0.0.1:8000`` and therefore failed with
``ConnectError`` in every CI run.

Model-dependent endpoints are not exercised here; see ``test_pipeline.py`` and
``test_image_processing.py`` for those.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import database
from app.security import create_session_token

SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'fisherman',
    created_at TEXT
);
CREATE TABLE user_stats (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    total_xp INTEGER DEFAULT 0,
    total_sightings INTEGER DEFAULT 0,
    total_species INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE identification_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT,
    result_sighting_id TEXT,
    linkage_json TEXT,
    artifact_dir TEXT,
    error_message TEXT
);
CREATE TABLE fish_sightings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fish_id TEXT NOT NULL,
    job_id TEXT,
    captured_at TEXT,
    created_at TEXT,
    location_lat REAL,
    location_lng REAL,
    catch_number INTEGER,
    previous_sighting_id TEXT,
    match_reference_sighting_id TEXT,
    linkage_json TEXT
);
CREATE TABLE fish_individuals (
    id TEXT PRIMARY KEY,
    fish_id TEXT NOT NULL,
    last_seen_at TEXT
);
"""


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated database and route the app's connections to it."""
    path = tmp_path / "integration.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO users (id, email, name, role) VALUES (?, ?, ?, ?)",
            [
                ("owner-1", "owner@example.com", "Owner", "fisherman"),
                ("other-1", "other@example.com", "Other", "fisherman"),
                ("researcher-1", "sci@example.com", "Scientist", "researcher"),
            ],
        )
        conn.execute(
            "INSERT INTO identification_jobs (id, user_id, status, created_at, "
            "result_sighting_id, artifact_dir, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "job-1",
                "owner-1",
                "completed",
                "2026-01-01T00:00:00+00:00",
                "sighting-1",
                "/srv/private/artifacts/job-1",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO fish_sightings (id, user_id, fish_id, job_id, captured_at, "
            "created_at, location_lat, location_lng, catch_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sighting-1",
                "owner-1",
                "CZ-401001-CYPCA-0001",
                "job-1",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                50.1,
                14.4,
                1,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    return path


@pytest.fixture
def client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Build a TestClient over the routers under test.

    The full ``app.main:app`` is deliberately avoided: its lifespan pre-loads
    every model, which is far too slow and requires checkpoints on disk.
    """
    from fastapi import FastAPI

    from app.routers import auth, jobs, sightings

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(jobs.router)
    app.include_router(sightings.router)
    # slowapi's decorator resolves the limiter from app.state at request time.
    app.state.limiter = auth.limiter
    return TestClient(app)


def _auth(user_id: str) -> dict[str, str]:
    """Authorization header carrying a valid signed session token."""
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


# ─────────────────────────────────────────────────────────────────────────────
# Health probes (mounted on the real app, no DB needed)
# ─────────────────────────────────────────────────────────────────────────────
def test_liveness_probe_reports_alive() -> None:
    from fastapi import FastAPI

    from app.main import health_live

    app = FastAPI()
    app.add_api_route("/health/live", health_live, methods=["GET"])
    with TestClient(app) as probe_client:
        response = probe_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"alive": True}


def test_health_reports_single_consistent_version() -> None:
    """
    /health used to report 2.1.0 while the app declared 2.0.0 and
    /health/detailed reported 3.0.0.
    """
    from fastapi import FastAPI

    from app.config import SERVICE_VERSION
    from app.main import health_check

    app = FastAPI()
    app.add_api_route("/health", health_check, methods=["GET"])
    with TestClient(app) as probe_client:
        payload = probe_client.get("/health").json()
    assert payload["version"] == SERVICE_VERSION
    assert payload["status"] == "healthy"


# ─────────────────────────────────────────────────────────────────────────────
# Species catalog (public reference data)
# ─────────────────────────────────────────────────────────────────────────────
def test_species_catalog_is_public_and_non_empty(client: TestClient) -> None:
    response = client.get("/api/v1/sightings/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert isinstance(catalog, list)
    assert len(catalog) > 0
    assert "slug" in catalog[0]


# ─────────────────────────────────────────────────────────────────────────────
# Registration / login
# ─────────────────────────────────────────────────────────────────────────────
def test_register_then_login_returns_usable_token(client: TestClient) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "New.User@Example.com",
            "password": "sufficient1password",
            "name": "New User",
        },
    )
    assert register.status_code == 201, register.text
    created = register.json()
    # Email is normalised to lowercase.
    assert created["email"] == "new.user@example.com"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "new.user@example.com", "password": "sufficient1password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == created["id"]


def test_register_cannot_self_assign_admin_role(client: TestClient) -> None:
    """
    Registration used to accept a client-supplied ``role``, allowing anyone to
    create an admin account.
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "escalate@example.com",
            "password": "sufficient1password",
            "name": "Escalation",
            "role": "admin",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "fisherman"


def test_register_rejects_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short", "name": "Weak"},
    )
    assert response.status_code == 422  # Pydantic min_length


def test_register_rejects_all_numeric_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "numeric@example.com", "password": "1234567890", "name": "Num"},
    )
    assert response.status_code == 400
    assert "letras y" in response.json()["detail"]


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "sufficient1password", "name": "X"},
    )
    assert response.status_code == 422


def test_login_with_unknown_email_and_wrong_password_are_indistinguishable(
    client: TestClient,
) -> None:
    """Identical responses prevent account enumeration."""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "known@example.com",
            "password": "sufficient1password",
            "name": "Known",
        },
    )

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "sufficient1password"},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "wrong1password"},
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_role_change_requires_admin(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/auth/users/other-1/role",
        json={"role": "admin"},
        headers=_auth("owner-1"),
    )
    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Job authorisation
# ─────────────────────────────────────────────────────────────────────────────
def test_job_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/job-1").status_code == 401


def test_job_owner_can_read_own_job(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/job-1", headers=_auth("owner-1"))
    assert response.status_code == 200
    assert response.json()["id"] == "job-1"


def test_other_user_cannot_read_someone_elses_job(client: TestClient) -> None:
    """This was an IDOR: the shared client secret used to be sufficient."""
    response = client.get("/api/v1/jobs/job-1", headers=_auth("other-1"))
    assert response.status_code == 403


def test_researcher_can_read_any_job(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/job-1", headers=_auth("researcher-1"))
    assert response.status_code == 200


def test_internal_fields_are_hidden_from_non_elevated_callers(
    client: TestClient,
) -> None:
    owner_payload = client.get("/api/v1/jobs/job-1", headers=_auth("owner-1")).json()
    for key in ("artifact_dir", "linkage_json", "error_message"):
        assert key not in owner_payload, f"{key} must not be exposed"

    elevated_payload = client.get(
        "/api/v1/jobs/job-1", headers=_auth("researcher-1")
    ).json()
    assert "artifact_dir" in elevated_payload


def test_missing_job_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/does-not-exist", headers=_auth("owner-1"))
    assert response.status_code == 404


def test_job_result_is_returned_to_owner(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/job-1/result", headers=_auth("owner-1"))
    assert response.status_code == 200
    assert response.json()["fish_id"] == "CZ-401001-CYPCA-0001"


def test_job_result_redacts_history_gps_for_fisherman(client: TestClient) -> None:
    """previous_catch/matched_reference_catch must not carry coordinates."""
    payload = client.get(
        "/api/v1/jobs/job-1/result", headers=_auth("owner-1")
    ).json()
    for nested_key in ("previous_catch", "matched_reference_catch"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            assert "location_lat" not in nested
            assert "location_lng" not in nested


def test_job_result_is_served_from_cache_on_repeat_request(
    client: TestClient,
) -> None:
    """The second poll must be a cache hit, not another set of DB reads."""
    from app.services.result_cache import get_result_cache

    cache = get_result_cache()
    cache.clear()

    first = client.get("/api/v1/jobs/job-1/result", headers=_auth("owner-1"))
    assert first.status_code == 200
    hits_before = cache.stats()["hits"]

    second = client.get("/api/v1/jobs/job-1/result", headers=_auth("owner-1"))
    assert second.status_code == 200
    assert second.json() == first.json()
    assert cache.stats()["hits"] == hits_before + 1


def test_cached_result_still_enforces_authorisation(client: TestClient) -> None:
    """A cache hit must not bypass the ownership check."""
    from app.services.result_cache import get_result_cache

    get_result_cache().clear()
    assert (
        client.get("/api/v1/jobs/job-1/result", headers=_auth("owner-1")).status_code
        == 200
    )
    assert (
        client.get("/api/v1/jobs/job-1/result", headers=_auth("other-1")).status_code
        == 403
    )


def test_upload_rejects_unknown_species(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs/upload",
        headers=_auth("owner-1"),
        files={"video": ("clip.mp4", b"\x00" * 64, "video/mp4")},
        data={
            "latitude": "50.1",
            "longitude": "14.4",
            "species_slug": "not_a_real_species",
        },
    )
    assert response.status_code == 422


def test_upload_rejects_out_of_range_coordinates(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs/upload",
        headers=_auth("owner-1"),
        files={"video": ("clip.mp4", b"\x00" * 64, "video/mp4")},
        data={
            "latitude": "999",
            "longitude": "14.4",
            "species_slug": "cyprinus_carpio",
        },
    )
    assert response.status_code == 422


def test_upload_rejects_mocked_gps(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs/upload",
        headers=_auth("owner-1"),
        files={"video": ("clip.mp4", b"\x00" * 64, "video/mp4")},
        data={
            "latitude": "50.1",
            "longitude": "14.4",
            "species_slug": "cyprinus_carpio",
            "gps_is_mocked": "true",
        },
    )
    assert response.status_code == 422


def test_upload_rejects_non_media_payload(client: TestClient) -> None:
    """A file whose bytes are not a known media container must be refused."""
    response = client.post(
        "/api/v1/jobs/upload",
        headers=_auth("owner-1"),
        files={"video": ("payload.mp4", b"<html><script>alert(1)</script></html>", "video/mp4")},
        data={
            "latitude": "50.1",
            "longitude": "14.4",
            "species_slug": "cyprinus_carpio",
        },
    )
    assert response.status_code == 400


def test_upload_requires_a_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs/upload",
        headers=_auth("owner-1"),
        data={
            "latitude": "50.1",
            "longitude": "14.4",
            "species_slug": "cyprinus_carpio",
        },
    )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Retired endpoint
# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_identify_endpoint_is_gone() -> None:
    from fastapi import FastAPI

    from app.routers import identify

    app = FastAPI()
    app.include_router(identify.router, prefix="/api/v1")
    with TestClient(app) as legacy_client:
        assert legacy_client.post("/api/v1/identify").status_code == 410
