"""
Dashboard job listing.

Covers the status filter, which is interpolated into the SQL WHERE clause as one
of two fixed literals while the value itself travels as a bound parameter. The
filter is now validated against a known set, so a typo returns 400 rather than an
empty list that an operator would read as "there are no jobs".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.routers import dashboard

SCHEMA = """
CREATE TABLE identification_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT,
    species_slug TEXT,
    area_code TEXT,
    latitude REAL,
    longitude REAL,
    preview_filename TEXT,
    artifact_dir TEXT,
    error_message TEXT
);
CREATE TABLE fish_sightings (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    preview_filename TEXT
);
"""

JOBS = [
    ("job-a", "uploaded", "2026-01-01T00:00:00+00:00"),
    ("job-b", "completed", "2026-01-02T00:00:00+00:00"),
    ("job-c", "completed", "2026-01-03T00:00:00+00:00"),
    ("job-d", "failed", "2026-01-04T00:00:00+00:00"),
    ("job-e", "repeat_capture", "2026-01-05T00:00:00+00:00"),
]

DASHBOARD_SECRET = "test-dashboard-secret"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient over the dashboard router with an isolated database."""
    db_path = tmp_path / "dashboard.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO identification_jobs (id, user_id, status, created_at) "
            "VALUES (?, 'user-1', ?, ?)",
            JOBS,
        )
        conn.commit()
    finally:
        conn.close()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    monkeypatch.setattr(dashboard, "get_db_connection", get_test_connection)
    monkeypatch.setattr(settings, "dashboard_secret", DASHBOARD_SECRET, raising=False)
    monkeypatch.setattr(settings, "skip_auth", False, raising=False)

    app = FastAPI()
    app.include_router(dashboard.router)
    return TestClient(app)


AUTH = {"X-FishDex-Dashboard-Secret": DASHBOARD_SECRET}


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────
def test_listing_requires_the_dashboard_secret(client: TestClient) -> None:
    assert client.get("/api/v1/dashboard/jobs").status_code == 401


def test_wrong_secret_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/dashboard/jobs",
        headers={"X-FishDex-Dashboard-Secret": "not-the-secret"},
    )
    assert response.status_code == 401


def test_secret_is_accepted_via_query_parameter(client: TestClient) -> None:
    """Kept for the existing dashboard, though the header is preferred."""
    response = client.get(f"/api/v1/dashboard/jobs?secret={DASHBOARD_SECRET}")
    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Status filter
# ─────────────────────────────────────────────────────────────────────────────
def test_unfiltered_listing_returns_every_job(client: TestClient) -> None:
    payload = client.get("/api/v1/dashboard/jobs", headers=AUTH).json()

    assert payload["total"] == len(JOBS)
    assert len(payload["jobs"]) == len(JOBS)


def test_status_filter_narrows_the_result(client: TestClient) -> None:
    payload = client.get(
        "/api/v1/dashboard/jobs?status=completed", headers=AUTH
    ).json()

    assert payload["total"] == 2
    assert {job["id"] for job in payload["jobs"]} == {"job-b", "job-c"}


@pytest.mark.parametrize("status", sorted(dashboard.JOB_STATUSES))
def test_every_known_status_is_accepted(client: TestClient, status: str) -> None:
    response = client.get(f"/api/v1/dashboard/jobs?status={status}", headers=AUTH)

    assert response.status_code == 200


def test_unknown_status_is_rejected_rather_than_returning_nothing(
    client: TestClient,
) -> None:
    """
    A typo used to yield an empty list, which an operator reads as "no jobs" and
    not "your filter is wrong".
    """
    response = client.get("/api/v1/dashboard/jobs?status=complete", headers=AUTH)

    assert response.status_code == 400
    assert "Unknown status" in response.json()["detail"]


def test_sql_metacharacters_in_the_filter_are_rejected(client: TestClient) -> None:
    """
    Defence in depth: the value is a bound parameter, so injection is impossible
    regardless, but the allow-list rejects it before the query is built.
    """
    response = client.get(
        "/api/v1/dashboard/jobs?status=' OR 1=1 --", headers=AUTH
    )

    assert response.status_code == 400


def test_all_jobs_remain_after_a_rejected_filter(client: TestClient) -> None:
    """A rejected filter must not have mutated anything."""
    client.get("/api/v1/dashboard/jobs?status=bogus", headers=AUTH)

    payload = client.get("/api/v1/dashboard/jobs", headers=AUTH).json()
    assert payload["total"] == len(JOBS)


# ─────────────────────────────────────────────────────────────────────────────
# Pagination
# ─────────────────────────────────────────────────────────────────────────────
def test_results_are_ordered_newest_first(client: TestClient) -> None:
    payload = client.get("/api/v1/dashboard/jobs", headers=AUTH).json()

    assert [job["id"] for job in payload["jobs"]] == [
        "job-e",
        "job-d",
        "job-c",
        "job-b",
        "job-a",
    ]


def test_limit_and_offset_walk_the_result_set(client: TestClient) -> None:
    first = client.get("/api/v1/dashboard/jobs?limit=2&offset=0", headers=AUTH).json()
    second = client.get("/api/v1/dashboard/jobs?limit=2&offset=2", headers=AUTH).json()

    assert [j["id"] for j in first["jobs"]] == ["job-e", "job-d"]
    assert [j["id"] for j in second["jobs"]] == ["job-c", "job-b"]


def test_has_more_reflects_the_remaining_pages(client: TestClient) -> None:
    first = client.get("/api/v1/dashboard/jobs?limit=2&offset=0", headers=AUTH).json()
    last = client.get("/api/v1/dashboard/jobs?limit=2&offset=4", headers=AUTH).json()

    assert first["has_more"] is True
    assert last["has_more"] is False


def test_total_is_the_filtered_count_not_the_table_count(client: TestClient) -> None:
    """Otherwise pagination over a filtered view reports the wrong page count."""
    payload = client.get(
        "/api/v1/dashboard/jobs?status=completed&limit=1", headers=AUTH
    ).json()

    assert payload["total"] == 2
    assert len(payload["jobs"]) == 1


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (501, 0), (10, -1)])
def test_out_of_range_pagination_is_rejected(
    client: TestClient, limit: int, offset: int
) -> None:
    response = client.get(
        f"/api/v1/dashboard/jobs?limit={limit}&offset={offset}", headers=AUTH
    )

    assert response.status_code == 422
