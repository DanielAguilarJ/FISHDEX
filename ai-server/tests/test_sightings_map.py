"""
Role-based visibility of sightings.

Covers the location-privacy rules: a fisherman may only see their own
geolocated captures, while researchers and admins see everything.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routers import sightings
from app.security import create_session_token


def _create_test_database(path: Path) -> None:
    """Populate a throwaway SQLite file with users and sightings fixtures."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT,
                name TEXT,
                role TEXT NOT NULL
            );

            CREATE TABLE fish_sightings (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                fish_id TEXT NOT NULL,
                species_english TEXT,
                rarity TEXT,
                captured_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                location_lat REAL,
                location_lng REAL,
                catch_number INTEGER
            );

            CREATE TABLE fish_individuals (
                id TEXT PRIMARY KEY,
                fish_id TEXT NOT NULL,
                species_english TEXT,
                last_seen_at TEXT,
                first_seen_lat REAL,
                first_seen_lng REAL,
                last_seen_lat REAL,
                last_seen_lng REAL,
                first_seen_by TEXT,
                last_seen_by TEXT
            );

            CREATE TABLE user_stats (
                id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                total_xp INTEGER DEFAULT 0,
                total_sightings INTEGER DEFAULT 0,
                total_species INTEGER DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO users (id, email, name, role) VALUES (?, ?, ?, ?)",
            [
                ("fisher-1", "f1@example.com", "Fisher One", "fisherman"),
                ("fisher-2", "f2@example.com", "Fisher Two", "fisherman"),
                ("researcher-1", "r1@example.com", "Researcher", "researcher"),
                ("admin-1", "a1@example.com", "Admin", "admin"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fish_sightings (
                id, user_id, fish_id, species_english, rarity,
                captured_at, created_at, location_lat, location_lng, catch_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "sighting-1",
                    "fisher-1",
                    "fish-a",
                    "Common carp",
                    "common",
                    "2026-01-01T10:00:00+00:00",
                    "2026-01-01T10:00:00+00:00",
                    50.100001,
                    14.400001,
                    1,
                ),
                (
                    "sighting-2",
                    "fisher-2",
                    "fish-a",
                    "Common carp",
                    "common",
                    "2026-02-01T10:00:00+00:00",
                    "2026-02-01T10:00:00+00:00",
                    50.200002,
                    14.500002,
                    2,
                ),
                (
                    "sighting-without-gps",
                    "fisher-2",
                    "fish-b",
                    "Northern pike",
                    "rare",
                    "2026-03-01T10:00:00+00:00",
                    "2026-03-01T10:00:00+00:00",
                    None,
                    None,
                    1,
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO fish_individuals (
                id, fish_id, species_english, last_seen_at,
                first_seen_lat, first_seen_lng, last_seen_lat, last_seen_lng,
                first_seen_by, last_seen_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "individual-1",
                "fish-a",
                "Common carp",
                "2026-02-01T10:00:00+00:00",
                50.100001,
                14.400001,
                50.200002,
                14.500002,
                "fisher-1",
                "fisher-2",
            ),
        )
        conn.execute(
            "INSERT INTO user_stats (id, user_id, total_xp, total_sightings, "
            "total_species, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("stats-1", "fisher-1", 250, 3, 2, "2026-03-01T10:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient wired to an isolated on-disk database."""
    database_path = tmp_path / "fishdex_test.sqlite"
    _create_test_database(database_path)

    def get_test_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(database_path)
        conn.row_factory = sqlite3.Row
        return conn

    # sightings.py and auth.py both reach the database through
    # app.database.db_session(), which resolves get_db_connection at call time.
    monkeypatch.setattr(database, "get_db_connection", get_test_connection)

    app = FastAPI()
    app.include_router(sightings.router)
    return TestClient(app)


def _headers(user_id: str) -> dict[str, str]:
    """Build an Authorization header holding a validly signed session token."""
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


def test_fisherman_map_contains_only_own_geolocated_captures(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/sightings/map", headers=_headers("fisher-1"))

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["sighting-1"]
    assert payload[0]["location_lat"] == pytest.approx(50.100001)
    assert payload[0]["location_lng"] == pytest.approx(14.400001)


def test_researcher_map_contains_all_geolocated_captures(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/sightings/map", headers=_headers("researcher-1"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["sighting-2", "sighting-1"]


def test_researcher_receives_chronological_history_for_same_fish(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/sightings/fish/fish-a/history", headers=_headers("researcher-1")
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["sighting-1", "sighting-2"]
    assert [item["catch_number"] for item in payload] == [1, 2]


def test_fisherman_cannot_open_full_fish_history(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sightings/fish/fish-a/history", headers=_headers("fisher-1")
    )

    assert response.status_code == 403


def test_fisherman_cannot_list_another_users_captures(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sightings/user/fisher-2", headers=_headers("fisher-1")
    )

    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Regressions for the authorisation holes found during the audit
# ─────────────────────────────────────────────────────────────────────────────
def test_unauthenticated_request_is_rejected(client: TestClient) -> None:
    """Every per-user endpoint must require a token, not just the app secret."""
    for path in (
        "/api/v1/sightings/map",
        "/api/v1/sightings/individuals",
        "/api/v1/sightings/stats/fisher-1",
        "/api/v1/sightings/user/fisher-1",
    ):
        assert client.get(path).status_code == 401, path


def test_forged_legacy_token_is_rejected(client: TestClient) -> None:
    """
    The previous token was base64(user_id) with no signature.

    Such a value must no longer authenticate anybody.
    """
    import base64

    forged = base64.b64encode(b"admin-1").decode()
    response = client.get(
        "/api/v1/sightings/map", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


def test_fisherman_cannot_read_another_users_stats(client: TestClient) -> None:
    """Stats used to be readable with only the shared client secret."""
    response = client.get(
        "/api/v1/sightings/stats/fisher-2", headers=_headers("fisher-1")
    )
    assert response.status_code == 403


def test_fisherman_stats_are_readable_by_owner(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sightings/stats/fisher-1", headers=_headers("fisher-1")
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_xp"] == 250
    # 250 XP → level 3 (100 XP per level, 1-based)
    assert payload["level"] == 3


def test_individuals_hide_gps_from_fisherman(client: TestClient) -> None:
    """
    Fish individuals used to leak first/last GPS to any caller.

    Non-elevated roles must receive the record without location columns.
    """
    response = client.get("/api/v1/sightings/individuals", headers=_headers("fisher-1"))

    assert response.status_code == 200
    record = response.json()[0]
    for key in (
        "first_seen_lat",
        "first_seen_lng",
        "last_seen_lat",
        "last_seen_lng",
        "first_seen_by",
        "last_seen_by",
    ):
        assert key not in record, f"{key} must be redacted for fishermen"
    assert record["fish_id"] == "fish-a"


def test_individuals_expose_gps_to_researcher(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sightings/individuals", headers=_headers("researcher-1")
    )

    assert response.status_code == 200
    record = response.json()[0]
    assert record["last_seen_lat"] == pytest.approx(50.200002)
    assert record["first_seen_by"] == "fisher-1"
