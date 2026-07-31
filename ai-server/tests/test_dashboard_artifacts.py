"""
Dashboard artifact and timeline endpoints.

These are the operator's audit surface: given a fish, show every capture of it,
where it was caught, and the evidence behind each match. They read JSON documents
out of the *private* data directory, which is the one place the server stores
per-fish records outside the database.

That makes ``_read_private_json`` the security-relevant part. The filename it
receives comes from a database column, but a column is not a trust boundary — a
poisoned value must not be able to read outside the private root or serve a
non-JSON file. Those defences are tested directly rather than only through the
endpoints.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.routers import dashboard
from app.routers.dashboard import _read_private_json

SCHEMA = """
CREATE TABLE identification_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    species_slug TEXT,
    area_code TEXT,
    area_name TEXT,
    latitude REAL,
    longitude REAL,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    result_sighting_id TEXT,
    result_fish_id TEXT,
    confidence REAL,
    preview_filename TEXT,
    annotated_preview_filename TEXT,
    artifact_dir TEXT,
    document_filename TEXT,
    linkage_json TEXT,
    media_type TEXT,
    raw_media_filename TEXT
);
CREATE TABLE fish_sightings (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    job_id TEXT,
    fish_id TEXT,
    species_slug TEXT,
    species_english TEXT,
    catch_number INTEGER,
    captured_at TEXT,
    created_at TEXT,
    location_lat REAL,
    location_lng REAL,
    size_cm REAL,
    weather TEXT,
    confidence REAL,
    preview_filename TEXT,
    video_filename TEXT,
    document_filename TEXT,
    linkage_json TEXT
);
CREATE TABLE fish_individuals (
    id TEXT PRIMARY KEY,
    fish_id TEXT UNIQUE,
    total_sightings INTEGER DEFAULT 1,
    last_seen_at TEXT
);
"""

DASHBOARD_SECRET = "dashboard-secret-for-tests"
AUTH = {"X-FishDex-Dashboard-Secret": DASHBOARD_SECRET}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """
    Build an isolated database plus a private data directory.

    Returns a dict with the database path and the private root, so tests can plant
    documents on disk.
    """
    db_path = tmp_path / "dashboard.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

    private_root = tmp_path / "private"
    private_root.mkdir()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    monkeypatch.setattr(dashboard, "get_db_connection", get_test_connection)
    monkeypatch.setattr(settings, "private_data_dir", str(private_root), raising=False)
    monkeypatch.setattr(settings, "dashboard_secret", DASHBOARD_SECRET, raising=False)
    monkeypatch.setattr(settings, "skip_auth", False, raising=False)

    return {"db": db_path, "private": private_root}


@pytest.fixture
def client(env: dict) -> TestClient:
    """TestClient over the dashboard router."""
    app = FastAPI()
    app.include_router(dashboard.router)
    return TestClient(app)


def insert_job(db: Path, job_id: str, **overrides: object) -> None:
    """Insert a job row with defaults."""
    row: dict = {
        "id": job_id,
        "user_id": "user-1",
        "status": "completed",
        "created_at": "2026-01-01T00:00:00+00:00",
        "species_slug": "cyprinus_carpio",
        "result_sighting_id": f"sighting-{job_id}",
        "result_fish_id": "CZ-401001-CYPCA-0001",
        "confidence": 0.92,
    }
    row.update(overrides)  # type: ignore[arg-type]
    conn = sqlite3.connect(db)
    try:
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO identification_jobs ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()


def insert_sighting(db: Path, sighting_id: str, **overrides: object) -> None:
    """Insert a sighting row with defaults."""
    row: dict = {
        "id": sighting_id,
        "user_id": "user-1",
        "job_id": f"job-{sighting_id}",
        "fish_id": "CZ-401001-CYPCA-0001",
        "species_slug": "cyprinus_carpio",
        "species_english": "Common carp",
        "catch_number": 1,
        "captured_at": "2026-01-01T10:00:00+00:00",
        "created_at": "2026-01-01T10:00:00+00:00",
        "location_lat": 50.1,
        "location_lng": 14.4,
        "confidence": 0.9,
    }
    row.update(overrides)  # type: ignore[arg-type]
    conn = sqlite3.connect(db)
    try:
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO fish_sightings ({columns}) VALUES ({placeholders})",
            tuple(row.values()),
        )
        conn.commit()
    finally:
        conn.close()


def plant_document(private_root: Path, relative: str, payload: dict) -> None:
    """Write a JSON document inside the private root."""
    path = private_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# _read_private_json — path containment
# ─────────────────────────────────────────────────────────────────────────────
def test_private_read_returns_the_document(env: dict) -> None:
    plant_document(env["private"], "fish_documents/401001/document.json", {"ok": True})

    assert _read_private_json("fish_documents/401001/document.json") == {"ok": True}


def test_private_read_of_none_is_none(env: dict) -> None:
    assert _read_private_json(None) is None


def test_private_read_of_empty_string_is_none(env: dict) -> None:
    assert _read_private_json("") is None


def test_private_read_of_a_missing_file_is_none(env: dict) -> None:
    """A document that was never written is absent, not an error."""
    assert _read_private_json("fish_documents/nope/document.json") is None


@pytest.mark.parametrize(
    "traversal",
    [
        "../../../etc/passwd.json",
        "fish_documents/../../secret.json",
        "..\\..\\windows\\evil.json",
        "/etc/passwd.json",
        "/absolute/path.json",
    ],
)
def test_private_read_rejects_path_traversal(env: dict, traversal: str) -> None:
    """
    The filename comes from a database column, and a column is not a trust
    boundary: a poisoned value must not reach outside the private root.
    """
    with pytest.raises(HTTPException) as excinfo:
        _read_private_json(traversal)

    assert excinfo.value.status_code == 400


def test_private_read_rejects_a_non_json_file(env: dict) -> None:
    """
    Restricting to .json stops this endpoint from becoming a generic file reader
    for anything inside the private directory — including .env or key material.
    """
    (env["private"] / "secrets.pem").write_text("-----BEGIN KEY-----", encoding="utf-8")

    with pytest.raises(HTTPException) as excinfo:
        _read_private_json("secrets.pem")

    assert excinfo.value.status_code == 400


def test_private_read_normalises_windows_separators(env: dict) -> None:
    plant_document(env["private"], "fish_documents/a/document.json", {"v": 1})

    assert _read_private_json("fish_documents\\a\\document.json") == {"v": 1}


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────
def test_status_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/dashboard/status").status_code == 401


def test_status_reports_job_counts_by_state(client: TestClient, env: dict) -> None:
    insert_job(env["db"], "job-1", status="uploaded")
    insert_job(env["db"], "job-2", status="completed")
    insert_job(env["db"], "job-3", status="completed")
    insert_job(env["db"], "job-4", status="failed")

    payload = client.get("/api/v1/dashboard/status", headers=AUTH).json()

    assert payload["jobs"]["completed"] == 2
    assert payload["jobs"]["failed"] == 1


def test_status_reports_model_availability(client: TestClient) -> None:
    """
    Reports rather than asserts: an operator needs to see a missing model, and the
    endpoint must answer even when nothing is loaded.
    """
    payload = client.get("/api/v1/dashboard/status", headers=AUTH).json()

    assert "models" in payload
    assert "detector" in payload["models"]


def test_status_includes_system_metrics(client: TestClient) -> None:
    payload = client.get("/api/v1/dashboard/status", headers=AUTH).json()

    assert isinstance(payload, dict)
    assert payload["jobs"]["queued"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# /jobs/{id}/detail
# ─────────────────────────────────────────────────────────────────────────────
def test_job_detail_requires_authentication(client: TestClient, env: dict) -> None:
    insert_job(env["db"], "job-1")

    assert client.get("/api/v1/dashboard/jobs/job-1/detail").status_code == 401


def test_job_detail_returns_the_job_row(client: TestClient, env: dict) -> None:
    insert_job(env["db"], "job-1", confidence=0.87)

    payload = client.get("/api/v1/dashboard/jobs/job-1/detail", headers=AUTH).json()

    assert payload["job"]["id"] == "job-1"
    assert payload["job"]["confidence"] == pytest.approx(0.87)


def test_job_detail_attaches_the_linked_sighting(client: TestClient, env: dict) -> None:
    """The sighting is resolved by its job_id foreign key, not by result_sighting_id."""
    insert_sighting(env["db"], "sighting-1", job_id="job-1", catch_number=3)
    insert_job(env["db"], "job-1", result_sighting_id="sighting-1")

    payload = client.get("/api/v1/dashboard/jobs/job-1/detail", headers=AUTH).json()

    assert payload["sighting"] is not None
    assert payload["sighting"]["catch_number"] == 3


def test_job_detail_attaches_the_fish_individual(client: TestClient, env: dict) -> None:
    conn = sqlite3.connect(env["db"])
    try:
        conn.execute(
            "INSERT INTO fish_individuals (id, fish_id, total_sightings, last_seen_at) "
            "VALUES (?, ?, ?, ?)",
            ("ind-1", "CZ-401001-CYPCA-0001", 4, "2026-02-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()
    insert_job(env["db"], "job-1", result_fish_id="CZ-401001-CYPCA-0001")

    payload = client.get("/api/v1/dashboard/jobs/job-1/detail", headers=AUTH).json()

    assert payload["individual"]["total_sightings"] == 4


def test_job_detail_resolves_the_document_and_manifest(
    client: TestClient, env: dict
) -> None:
    """
    The manifest path is derived from the document path by filename substitution.
    Pinning it guards a rename of either file silently breaking the lookup.
    """
    plant_document(env["private"], "fd/document.json", {"schema_version": "1.1"})
    plant_document(env["private"], "fd/manifest.json", {"artifacts": 7})
    insert_job(env["db"], "job-1", document_filename="fd/document.json")

    payload = client.get("/api/v1/dashboard/jobs/job-1/detail", headers=AUTH).json()

    assert payload["document"]["schema_version"] == "1.1"
    assert payload["manifest"]["artifacts"] == 7


def test_job_detail_of_an_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/dashboard/jobs/absent/detail", headers=AUTH).status_code == 404


def test_job_detail_tolerates_a_missing_sighting(client: TestClient, env: dict) -> None:
    """A job whose sighting row was deleted must still be inspectable."""
    insert_job(env["db"], "job-1", result_sighting_id="deleted-sighting")

    response = client.get("/api/v1/dashboard/jobs/job-1/detail", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["sighting"] is None


# ─────────────────────────────────────────────────────────────────────────────
# /jobs/{id}/document
# ─────────────────────────────────────────────────────────────────────────────
def test_job_document_returns_the_stored_document(
    client: TestClient, env: dict
) -> None:
    plant_document(
        env["private"], "fish_documents/401001/document.json", {"schema_version": "1.1"}
    )
    insert_job(
        env["db"], "job-1", document_filename="fish_documents/401001/document.json"
    )

    payload = client.get("/api/v1/dashboard/jobs/job-1/document", headers=AUTH).json()

    # Returned unwrapped, not nested under a "document" key.
    assert payload["schema_version"] == "1.1"


def test_job_document_of_an_unknown_job_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/jobs/absent/document", headers=AUTH)

    assert response.status_code == 404


def test_job_document_rejects_a_traversal_stored_in_the_column(
    client: TestClient, env: dict
) -> None:
    """
    Defence in depth: even if a hostile value reaches the column, the read is
    refused rather than serving a file from outside the private root.
    """
    insert_job(env["db"], "job-1", document_filename="../../../etc/passwd.json")

    response = client.get("/api/v1/dashboard/jobs/job-1/document", headers=AUTH)

    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# /fish/{id}/manifest
# ─────────────────────────────────────────────────────────────────────────────
def test_fish_manifest_lists_every_capture(client: TestClient, env: dict) -> None:
    insert_sighting(env["db"], "s1", catch_number=1, captured_at="2026-01-01T00:00:00+00:00")
    insert_sighting(env["db"], "s2", catch_number=2, captured_at="2026-02-01T00:00:00+00:00")

    payload = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/manifest", headers=AUTH
    ).json()

    assert payload["total_captures"] == 2


def test_fish_manifest_is_newest_first(client: TestClient, env: dict) -> None:
    insert_sighting(env["db"], "s1", catch_number=1, captured_at="2026-01-01T00:00:00+00:00")
    insert_sighting(env["db"], "s2", catch_number=2, captured_at="2026-02-01T00:00:00+00:00")

    payload = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/manifest", headers=AUTH
    ).json()

    assert [c["sighting"]["id"] for c in payload["captures"]] == ["s2", "s1"]


def test_fish_manifest_resolves_the_manifest_document(
    client: TestClient, env: dict
) -> None:
    """
    The manifest path is derived from the document path by filename substitution,
    which is worth pinning: a change to either name silently breaks the lookup.
    """
    plant_document(
        env["private"], "fish_documents/401001/manifest.json", {"artifacts": 4}
    )
    insert_sighting(
        env["db"],
        "s1",
        document_filename="fish_documents/401001/document.json",
    )

    payload = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/manifest", headers=AUTH
    ).json()

    assert payload["captures"][0]["manifest"] == {"artifacts": 4}


def test_fish_manifest_of_an_unknown_fish_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/fish/CZ-NOPE-0000/manifest", headers=AUTH)

    assert response.status_code == 404


def test_fish_manifest_tolerates_a_missing_manifest_file(
    client: TestClient, env: dict
) -> None:
    """A sighting whose artifacts were pruned must still appear in the list."""
    insert_sighting(
        env["db"], "s1", document_filename="fish_documents/gone/document.json"
    )

    payload = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/manifest", headers=AUTH
    ).json()

    assert payload["captures"][0]["manifest"] is None


def test_fish_manifest_requires_authentication(client: TestClient, env: dict) -> None:
    insert_sighting(env["db"], "s1")

    response = client.get("/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/manifest")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# /fish/{id}/timeline
# ─────────────────────────────────────────────────────────────────────────────
def test_timeline_is_ordered_by_catch_number(client: TestClient, env: dict) -> None:
    """
    The timeline drives the map trajectory and the growth chart, so chronological
    order is the whole point.
    """
    for catch in (3, 1, 2):
        insert_sighting(env["db"], f"s{catch}", catch_number=catch)

    payload = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline", headers=AUTH
    ).json()

    assert [e["catch_number"] for e in payload["timeline"]] == [1, 2, 3]


def test_timeline_builds_media_urls(client: TestClient, env: dict) -> None:
    insert_sighting(
        env["db"],
        "s1",
        preview_filename="jobs/abc/preview.jpg",
        video_filename="raw_videos/abc.mp4",
    )

    event = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline", headers=AUTH
    ).json()["timeline"][0]

    assert event["preview_url"] == "/storage/jobs/abc/preview.jpg"
    assert event["video_url"] == "/storage/raw_videos/abc.mp4"


def test_timeline_normalises_windows_separators_in_urls(
    client: TestClient, env: dict
) -> None:
    """Paths are built with pathlib; a URL with backslashes does not resolve."""
    insert_sighting(env["db"], "s1", preview_filename="jobs\\abc\\preview.jpg")

    event = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline", headers=AUTH
    ).json()["timeline"][0]

    assert event["preview_url"] == "/storage/jobs/abc/preview.jpg"


def test_timeline_media_urls_are_null_when_absent(client: TestClient, env: dict) -> None:
    """Null rather than '/storage/None', which the client would try to fetch."""
    insert_sighting(env["db"], "s1", preview_filename=None, video_filename=None)

    event = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline", headers=AUTH
    ).json()["timeline"][0]

    assert event["preview_url"] is None
    assert event["video_url"] is None


def test_timeline_of_an_unknown_fish_is_empty_not_an_error(
    client: TestClient,
) -> None:
    """
    An empty timeline is a meaningful answer (a catalogued fish with no stored
    sightings), so it is not a 404.
    """
    payload = client.get(
        "/api/v1/dashboard/fish/CZ-NOPE-0000/timeline", headers=AUTH
    ).json()

    assert payload["total_captures"] == 0
    assert payload["timeline"] == []


def test_timeline_carries_the_location_for_the_map(client: TestClient, env: dict) -> None:
    insert_sighting(env["db"], "s1", location_lat=50.123456, location_lng=14.654321)

    event = client.get(
        "/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline", headers=AUTH
    ).json()["timeline"][0]

    assert event["location_lat"] == pytest.approx(50.123456)
    assert event["location_lng"] == pytest.approx(14.654321)


def test_timeline_requires_authentication(client: TestClient, env: dict) -> None:
    insert_sighting(env["db"], "s1")

    response = client.get("/api/v1/dashboard/fish/CZ-401001-CYPCA-0001/timeline")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# /jobs/{id}/retry
# ─────────────────────────────────────────────────────────────────────────────
def test_retry_requires_authentication(client: TestClient, env: dict) -> None:
    insert_job(env["db"], "job-1", status="failed")

    assert client.post("/api/v1/dashboard/jobs/job-1/retry").status_code == 401


def test_retry_dispatches_to_a_worker_thread(
    client: TestClient, env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The regression this covers: the handler used to call the synchronous processor
    directly, blocking the event loop for the whole inference and freezing every
    other request.
    """
    import threading

    calls: list[tuple[str, bool, int]] = []

    def fake_process(job_id: str, force: bool = False) -> dict:
        calls.append((job_id, force, threading.get_ident()))
        return {"status": "completed", "job_id": job_id}

    monkeypatch.setattr(dashboard, "process_identification_job", fake_process)
    insert_job(env["db"], "job-1", status="failed")

    response = client.post("/api/v1/dashboard/jobs/job-1/retry", headers=AUTH)

    assert response.status_code == 200
    assert calls[0][0] == "job-1"
    assert calls[0][1] is True  # retry always forces
    # Ran off the main thread, which is what asyncio.to_thread guarantees.
    assert calls[0][2] != threading.get_ident()


def test_retry_failure_does_not_leak_internal_detail(
    client: TestClient, env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stack-trace string in the response body is information disclosure."""

    def fake_process(job_id: str, force: bool = False) -> dict:
        raise RuntimeError("/srv/private/artifacts leaked path")

    monkeypatch.setattr(dashboard, "process_identification_job", fake_process)
    insert_job(env["db"], "job-1", status="failed")

    response = client.post("/api/v1/dashboard/jobs/job-1/retry", headers=AUTH)

    assert response.status_code == 500
    assert "leaked path" not in response.text
    assert "/srv" not in response.text


def test_job_document_is_404_when_the_file_is_absent(
    client: TestClient, env: dict
) -> None:
    """
    A job row that references a document the artifacts pass never wrote. 404 is
    correct: the job exists but its evidence does not.
    """
    insert_job(env["db"], "job-1", document_filename="fd/never_written.json")

    response = client.get("/api/v1/dashboard/jobs/job-1/document", headers=AUTH)

    assert response.status_code == 404


def test_job_document_is_404_when_the_column_is_null(
    client: TestClient, env: dict
) -> None:
    insert_job(env["db"], "job-1", document_filename=None)

    response = client.get("/api/v1/dashboard/jobs/job-1/document", headers=AUTH)

    assert response.status_code == 404
