import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import sightings
from app.routers.auth import generate_token


def _create_test_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
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
            """
        )
        conn.executemany(
            "INSERT INTO users (id, role) VALUES (?, ?)",
            [
                ("fisher-1", "fisherman"),
                ("fisher-2", "fisherman"),
                ("researcher-1", "researcher"),
                ("admin-1", "admin"),
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
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "fishdex_test.sqlite"
    _create_test_database(database_path)

    def get_test_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(database_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(sightings, "get_db_connection", get_test_connection)

    app = FastAPI()
    app.include_router(sightings.router)
    return TestClient(app)


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {generate_token(user_id)}"}


def test_fisherman_map_contains_only_own_geolocated_captures(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/sightings/map",
        headers=_headers("fisher-1"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["sighting-1"]
    assert payload[0]["location_lat"] == pytest.approx(50.100001)
    assert payload[0]["location_lng"] == pytest.approx(14.400001)


def test_researcher_map_contains_all_geolocated_captures(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/sightings/map",
        headers=_headers("researcher-1"),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "sighting-2",
        "sighting-1",
    ]


def test_researcher_receives_chronological_history_for_same_fish(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/sightings/fish/fish-a/history",
        headers=_headers("researcher-1"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["sighting-1", "sighting-2"]
    assert [item["catch_number"] for item in payload] == [1, 2]


def test_fisherman_cannot_open_full_fish_history(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sightings/fish/fish-a/history",
        headers=_headers("fisher-1"),
    )

    assert response.status_code == 403


def test_fisherman_cannot_list_another_users_captures(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/sightings/user/fisher-2",
        headers=_headers("fisher-1"),
    )

    assert response.status_code == 403
