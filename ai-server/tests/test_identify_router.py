"""
Reference-data and legacy identification endpoints.

Two of these endpoints carry the location-privacy rules that the audit found
broken. ``/fish/{id}/history`` had no authentication at all and took the caller's
role from a query parameter, so anyone could request ``?user_role=researcher`` and
receive the recapture coordinates of any fish — the exact information a poacher
would want. ``/health/detailed`` disclosed model paths, matching thresholds and
gallery size to unauthenticated callers.

The rest is genuinely public reference data: the official Czech revír catalog and
the species list, neither of which contains user or individual-fish information.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.routers import identify
from app.security import create_session_token

SCHEMA = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT,
    name TEXT,
    role TEXT NOT NULL
);
"""

USERS = [
    ("fisher-1", "f@example.com", "Fisher", "fisherman"),
    ("researcher-1", "r@example.com", "Researcher", "researcher"),
    ("admin-1", "a@example.com", "Admin", "admin"),
]


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the disk storage root at a temporary directory."""
    root = tmp_path / "server-data"
    root.mkdir()
    monkeypatch.setattr(settings, "server_data_dir", str(root), raising=False)
    return root


@pytest.fixture
def client(tmp_path: Path, storage: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient over the identify router with an isolated user table."""
    db_path = tmp_path / "identify.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO users (id, email, name, role) VALUES (?,?,?,?)", USERS)
        conn.commit()
    finally:
        conn.close()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)

    app = FastAPI()
    app.include_router(identify.router, prefix="/api/v1")
    return TestClient(app)


def auth(user_id: str) -> dict[str, str]:
    """Authorization header with a validly signed session token."""
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


def add_fish(root: Path, area: str, species: str, fish_id: str, catches: int = 1) -> None:
    """Create a fish with N catches in the disk store."""
    import json

    for catch in range(1, catches + 1):
        catch_dir = root / area / species / fish_id / f"catch_{catch}"
        (catch_dir / "images").mkdir(parents=True, exist_ok=True)
        (catch_dir / "data.json").write_text(
            json.dumps({"saved_at": f"2026-0{catch}-01T10:00:00+00:00", "catch_number": catch}),
            encoding="utf-8",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Retired endpoint
# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_identify_is_gone(client: TestClient) -> None:
    """
    Retired rather than fixed: it lacked calibration gating and could contaminate
    the identity gallery.
    """
    response = client.post("/api/v1/identify")

    assert response.status_code == 410
    assert "jobs/upload" in response.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Public reference data
# ─────────────────────────────────────────────────────────────────────────────
def test_species_catalog_is_public(client: TestClient) -> None:
    response = client.get("/api/v1/species")

    assert response.status_code == 200
    assert response.json()["count"] > 0


def test_species_catalog_entries_carry_names(client: TestClient) -> None:
    species = client.get("/api/v1/species").json()["species"][0]

    assert species["english_name"]
    assert species["slug"]


def test_area_search_is_public(client: TestClient) -> None:
    """The official revír catalog contains no user or individual-fish data."""
    response = client.get("/api/v1/areas/search?lat=50.08&lon=14.44&radius_km=25")

    assert response.status_code == 200
    assert "areas" in response.json()


def test_area_search_echoes_the_radius(client: TestClient) -> None:
    payload = client.get("/api/v1/areas/search?lat=50.0&lon=14.0&radius_km=7.5").json()

    assert payload["radius_km"] == pytest.approx(7.5)


def test_area_search_count_matches_the_list(client: TestClient) -> None:
    payload = client.get("/api/v1/areas/search?lat=50.0&lon=14.0&radius_km=50").json()

    assert payload["count"] == len(payload["areas"])


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(91, 14.0), (-91, 14.0), (50.0, 181), (50.0, -181)],
)
def test_area_search_rejects_out_of_range_coordinates(
    client: TestClient, lat: float, lon: float
) -> None:
    """
    Validated by FastAPI at the boundary. Previously unbounded, so a client could
    request coordinates that cannot exist.
    """
    response = client.get(f"/api/v1/areas/search?lat={lat}&lon={lon}")

    assert response.status_code == 422


@pytest.mark.parametrize("radius", [0, -5, 101, 1000])
def test_area_search_rejects_an_out_of_range_radius(
    client: TestClient, radius: float
) -> None:
    """An unbounded radius would scan the whole catalog on every request."""
    response = client.get(f"/api/v1/areas/search?lat=50.0&lon=14.0&radius_km={radius}")

    assert response.status_code == 422


def test_area_search_requires_coordinates(client: TestClient) -> None:
    assert client.get("/api/v1/areas/search").status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Area statistics — authenticated
# ─────────────────────────────────────────────────────────────────────────────
def test_area_stats_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/areas/401001/stats").status_code == 401


def test_area_stats_are_available_to_a_fisherman(
    client: TestClient, storage: Path
) -> None:
    """Aggregate only: counts and species, never individual fish locations."""
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catches=2)

    payload = client.get("/api/v1/areas/401001/stats", headers=auth("fisher-1")).json()

    assert payload["total_fish"] == 1
    assert payload["total_catches"] == 2


def test_area_stats_include_the_species_breakdown(
    client: TestClient, storage: Path
) -> None:
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    add_fish(storage, "401001", "esox_lucius", "CZ-401001-ESOLU-0001")

    payload = client.get("/api/v1/areas/401001/stats", headers=auth("fisher-1")).json()

    assert payload["species_breakdown"] == {"cyprinus_carpio": 1, "esox_lucius": 1}


def test_area_stats_are_zeroed_for_an_empty_area(client: TestClient) -> None:
    payload = client.get("/api/v1/areas/999999/stats", headers=auth("fisher-1")).json()

    assert payload["total_fish"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Species in an area — authenticated
# ─────────────────────────────────────────────────────────────────────────────
def test_area_species_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/areas/401001/species").status_code == 401


def test_area_species_lists_what_is_stored(client: TestClient, storage: Path) -> None:
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    payload = client.get(
        "/api/v1/areas/401001/species", headers=auth("fisher-1")
    ).json()

    assert payload["count"] == 1
    assert payload["species"][0]["slug"] == "cyprinus_carpio"


def test_area_species_falls_back_for_an_unknown_slug(
    client: TestClient, storage: Path
) -> None:
    """
    A directory whose name is not in the catalog still appears, with a derived
    readable name. Dropping it would hide data that exists on disk.
    """
    add_fish(storage, "401001", "unlisted_species", "CZ-401001-UNLIS-0001")

    payload = client.get(
        "/api/v1/areas/401001/species", headers=auth("fisher-1")
    ).json()

    assert payload["species"][0]["slug"] == "unlisted_species"
    assert payload["species"][0]["english_name"] == "Unlisted Species"


def test_area_species_is_empty_for_an_unknown_area(client: TestClient) -> None:
    payload = client.get(
        "/api/v1/areas/999999/species", headers=auth("fisher-1")
    ).json()

    assert payload["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Fish history — the location-privacy boundary
# ─────────────────────────────────────────────────────────────────────────────
def test_fish_history_requires_authentication(client: TestClient) -> None:
    """
    Previously open: the endpoint had no auth dependency and read the caller's role
    from a query parameter.
    """
    assert client.get("/api/v1/fish/CZ-401001-CYPCA-0001/history").status_code == 401


def test_fisherman_cannot_read_a_fish_history(client: TestClient, storage: Path) -> None:
    """The history discloses the recapture locations of an individual animal."""
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catches=2)

    response = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history", headers=auth("fisher-1")
    )

    assert response.status_code == 403


def test_a_client_supplied_role_cannot_escalate(client: TestClient, storage: Path) -> None:
    """
    The exact bypass that existed: '?user_role=researcher' used to be believed.
    The parameter is now ignored entirely and the role comes from the database.
    """
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    response = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history?user_role=researcher",
        headers=auth("fisher-1"),
    )

    assert response.status_code == 403


def test_researcher_can_read_a_fish_history(client: TestClient, storage: Path) -> None:
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001", catches=3)

    payload = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history", headers=auth("researcher-1")
    ).json()

    assert payload["fish_id"] == "CZ-401001-CYPCA-0001"
    assert payload["total_catches"] == 3


def test_admin_can_read_a_fish_history(client: TestClient, storage: Path) -> None:
    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")

    response = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history", headers=auth("admin-1")
    )

    assert response.status_code == 200


def test_unknown_fish_is_404_for_an_authorised_caller(client: TestClient) -> None:
    response = client.get(
        "/api/v1/fish/CZ-NOPE-0000/history", headers=auth("researcher-1")
    )

    assert response.status_code == 404


def test_a_forged_token_cannot_read_a_fish_history(
    client: TestClient, storage: Path
) -> None:
    """The old token scheme was base64(user_id) with no signature."""
    import base64

    add_fish(storage, "401001", "cyprinus_carpio", "CZ-401001-CYPCA-0001")
    forged = base64.b64encode(b"admin-1").decode()

    response = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


def test_a_token_for_a_deleted_user_is_rejected(client: TestClient) -> None:
    """A validly signed token for an account that no longer exists must not work."""
    response = client.get(
        "/api/v1/fish/CZ-401001-CYPCA-0001/history", headers=auth("deleted-user")
    )

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Detailed health — reconnaissance surface
# ─────────────────────────────────────────────────────────────────────────────
def test_detailed_health_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/health/detailed").status_code == 401


def test_fisherman_cannot_read_detailed_health(client: TestClient) -> None:
    """
    Discloses configured model paths, matching thresholds and gallery size — useful
    reconnaissance, and not needed by the mobile client.
    """
    response = client.get("/api/v1/health/detailed", headers=auth("fisher-1"))

    assert response.status_code == 403


def test_researcher_can_read_detailed_health(client: TestClient) -> None:
    payload = client.get(
        "/api/v1/health/detailed", headers=auth("researcher-1")
    ).json()

    assert payload["status"] == "healthy"
    assert "reid_similarity_threshold" in payload


def test_detailed_health_reports_a_single_service_version(client: TestClient) -> None:
    """Three endpoints used to report 2.0.0, 2.1.0 and 3.0.0."""
    from app.config import SERVICE_VERSION

    payload = client.get(
        "/api/v1/health/detailed", headers=auth("researcher-1")
    ).json()

    assert payload["version"] == SERVICE_VERSION


def test_detailed_health_does_not_force_a_model_load(client: TestClient) -> None:
    """
    Reports loaded/not-loaded via the non-forcing accessors, so an operator probe
    cannot trigger a multi-hundred-megabyte load.
    """
    payload = client.get(
        "/api/v1/health/detailed", headers=auth("researcher-1")
    ).json()

    assert payload["obb_model_loaded"] is False
    assert payload["reid_model_loaded"] is False
