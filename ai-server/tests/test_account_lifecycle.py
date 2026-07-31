"""
Account lifecycle: registration, login, and administrative role changes.

The role endpoint is the replacement for a privilege-escalation hole: registration
used to accept a client-supplied ``role``, so anyone could create an admin account
by adding one field to the signup request. Elevation is now an administrative
operation, and these tests pin that only an admin can perform it.

The other property covered here is the transparent hash upgrade. Accounts created
before this audit used 100 000 PBKDF2 iterations; they must keep working, and be
silently migrated to 600 000 on their next successful login — without ever
rejecting a login because the migration failed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routers import auth as auth_router
from app.security import PBKDF2_ITERATIONS, create_session_token, verify_password

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
"""


def legacy_hash(password: str) -> str:
    """Reproduce the pre-audit 100k-iteration hash format."""
    salt = b"\x02" * 16
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}:{key.hex()}"


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated user database with one account per role."""
    path = tmp_path / "auth.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO users (id, email, password_hash, name, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("fisher-1", "f@example.com", legacy_hash("legacypassword1"),
                 "Fisher", "fisherman", "2026-01-01T00:00:00+00:00"),
                ("researcher-1", "r@example.com", legacy_hash("legacypassword1"),
                 "Researcher", "researcher", "2026-01-01T00:00:00+00:00"),
                ("admin-1", "a@example.com", legacy_hash("legacypassword1"),
                 "Admin", "admin", "2026-01-01T00:00:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(database, "get_db_connection", get_test_connection)
    monkeypatch.setattr(auth_router, "get_db_connection", get_test_connection)
    return path


@pytest.fixture
def client(db: Path) -> TestClient:
    """TestClient over the auth router."""
    app = FastAPI()
    app.include_router(auth_router.router)
    app.state.limiter = auth_router.limiter
    return TestClient(app)


def auth(user_id: str) -> dict[str, str]:
    """Authorization header with a validly signed session token."""
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


def read_user(db: Path, user_id: str) -> dict:
    """Read a user row as a dict."""
    conn = sqlite3.connect(db)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# /me
# ─────────────────────────────────────────────────────────────────────────────
def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_a_non_bearer_scheme(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )

    assert response.status_code == 401


def test_me_rejects_an_empty_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "})

    assert response.status_code == 401


def test_me_returns_the_authenticated_account(client: TestClient) -> None:
    payload = client.get("/api/v1/auth/me", headers=auth("researcher-1")).json()

    assert payload["id"] == "researcher-1"
    assert payload["role"] == "researcher"


def test_me_never_returns_the_password_hash(client: TestClient) -> None:
    """The response model is a whitelist, but this is worth pinning explicitly."""
    payload = client.get("/api/v1/auth/me", headers=auth("fisher-1")).json()

    assert "password_hash" not in payload


def test_me_rejects_a_token_for_a_deleted_account(client: TestClient) -> None:
    """
    A validly signed token outlives the account it names, so existence is
    re-checked on every request.
    """
    response = client.get("/api/v1/auth/me", headers=auth("no-such-user"))

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Login and hash upgrade
# ─────────────────────────────────────────────────────────────────────────────
def test_login_with_a_legacy_hash_succeeds(client: TestClient) -> None:
    """Accounts predating this audit must keep working."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "f@example.com", "password": "legacypassword1"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "fisher-1"


def test_login_upgrades_a_legacy_hash_in_place(client: TestClient, db: Path) -> None:
    """
    The migration is opportunistic and invisible: the user notices nothing, but the
    stored hash moves from 100k to 600k iterations.
    """
    before = read_user(db, "fisher-1")["password_hash"]
    assert ":" in before and "pbkdf2_sha256" not in before

    client.post(
        "/api/v1/auth/login",
        json={"email": "f@example.com", "password": "legacypassword1"},
    )

    after = read_user(db, "fisher-1")["password_hash"]
    assert after.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")
    assert verify_password("legacypassword1", after) is True


def test_the_upgraded_hash_still_authenticates(client: TestClient) -> None:
    """A second login must work against the newly written hash."""
    for _ in range(2):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "f@example.com", "password": "legacypassword1"},
        )
        assert response.status_code == 200


def test_a_failed_upgrade_does_not_reject_the_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The upgrade is best-effort. A user must never be locked out because the
    migration write failed.
    """

    def failing_upgrade(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(auth_router, "hash_password", failing_upgrade)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "f@example.com", "password": "legacypassword1"},
    )

    assert response.status_code == 200


def test_login_normalises_the_email_case(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "F@EXAMPLE.COM", "password": "legacypassword1"},
    )

    assert response.status_code == 200


def test_login_returns_a_usable_token(client: TestClient) -> None:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "f@example.com", "password": "legacypassword1"},
    ).json()["token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["id"] == "fisher-1"


def test_login_with_a_wrong_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "f@example.com", "password": "notthepassword1"},
    )

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────
def test_registration_creates_a_fisherman(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "adequate1password", "name": "New"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "fisherman"


def test_registration_ignores_a_requested_role(client: TestClient) -> None:
    """
    The privilege escalation this endpoint used to allow: role came straight from
    the request body.
    """
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "escalate@example.com",
            "password": "adequate1password",
            "name": "Escalation",
            "role": "admin",
        },
    )

    assert response.json()["role"] == "fisherman"


def test_registration_seeds_user_stats(client: TestClient, db: Path) -> None:
    """Both inserts share one transaction; a partial account would break the app."""
    user_id = client.post(
        "/api/v1/auth/register",
        json={"email": "stats@example.com", "password": "adequate1password", "name": "S"},
    ).json()["id"]

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT total_xp FROM user_stats WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == 0


def test_duplicate_registration_is_a_conflict(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "f@example.com", "password": "adequate1password", "name": "Dup"},
    )

    assert response.status_code == 409


def test_a_duplicate_conflict_does_not_disclose_schema_detail(
    client: TestClient,
) -> None:
    """
    The SQLite constraint name would name the table and column. The response is
    generic, which is why the exception is chained with 'from None'.
    """
    body = client.post(
        "/api/v1/auth/register",
        json={"email": "f@example.com", "password": "adequate1password", "name": "Dup"},
    ).text

    assert "UNIQUE" not in body
    assert "users" not in body


def test_a_duplicate_registration_creates_nothing(client: TestClient, db: Path) -> None:
    """The transaction must roll back cleanly, leaving no orphan stats row."""
    conn = sqlite3.connect(db)
    try:
        before = conn.execute("SELECT COUNT(*) FROM user_stats").fetchone()[0]
    finally:
        conn.close()

    client.post(
        "/api/v1/auth/register",
        json={"email": "f@example.com", "password": "adequate1password", "name": "Dup"},
    )

    conn = sqlite3.connect(db)
    try:
        after = conn.execute("SELECT COUNT(*) FROM user_stats").fetchone()[0]
    finally:
        conn.close()

    assert after == before


def test_registration_trims_the_display_name(client: TestClient) -> None:
    payload = client.post(
        "/api/v1/auth/register",
        json={"email": "trim@example.com", "password": "adequate1password", "name": "  Padded  "},
    ).json()

    assert payload["name"] == "Padded"


# ─────────────────────────────────────────────────────────────────────────────
# Administrative role changes
# ─────────────────────────────────────────────────────────────────────────────
def test_role_change_requires_authentication(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role", json={"role": "researcher"}
    )

    assert response.status_code == 401


def test_a_fisherman_cannot_change_roles(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role",
        json={"role": "admin"},
        headers=auth("fisher-1"),
    )

    assert response.status_code == 403


def test_a_researcher_cannot_change_roles(client: TestClient) -> None:
    """
    Researcher is elevated for reading data, not for administration. Conflating the
    two would let any researcher mint admins.
    """
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role",
        json={"role": "admin"},
        headers=auth("researcher-1"),
    )

    assert response.status_code == 403


def test_an_admin_can_promote_a_user(client: TestClient, db: Path) -> None:
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role",
        json={"role": "researcher"},
        headers=auth("admin-1"),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "researcher"
    assert read_user(db, "fisher-1")["role"] == "researcher"


def test_an_admin_can_demote_a_user(client: TestClient, db: Path) -> None:
    """Revocation must work, not only granting."""
    client.patch(
        "/api/v1/auth/users/researcher-1/role",
        json={"role": "fisherman"},
        headers=auth("admin-1"),
    )

    assert read_user(db, "researcher-1")["role"] == "fisherman"


@pytest.mark.parametrize("role", ["fisherman", "researcher", "admin"])
def test_every_assignable_role_is_accepted(
    client: TestClient, role: str
) -> None:
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role", json={"role": role}, headers=auth("admin-1")
    )

    assert response.status_code == 200


@pytest.mark.parametrize("bogus", ["superadmin", "root", "", "ADMIN", "owner"])
def test_an_unknown_role_is_rejected(client: TestClient, bogus: str) -> None:
    """
    An allow-list, not a denylist. Note case sensitivity: 'ADMIN' is not 'admin',
    so a case-mangled value cannot slip through.
    """
    response = client.patch(
        "/api/v1/auth/users/fisher-1/role", json={"role": bogus}, headers=auth("admin-1")
    )

    assert response.status_code == 400


def test_a_rejected_role_leaves_the_user_unchanged(
    client: TestClient, db: Path
) -> None:
    client.patch(
        "/api/v1/auth/users/fisher-1/role",
        json={"role": "superadmin"},
        headers=auth("admin-1"),
    )

    assert read_user(db, "fisher-1")["role"] == "fisherman"


def test_promoting_an_unknown_user_is_404(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/auth/users/no-such-user/role",
        json={"role": "admin"},
        headers=auth("admin-1"),
    )

    assert response.status_code == 404


def test_an_admin_can_demote_themselves(client: TestClient, db: Path) -> None:
    """
    Permitted deliberately, and worth documenting: there is no last-admin guard, so
    an operator can lock themselves out. Recorded here so the behaviour is a
    decision rather than an accident.
    """
    response = client.patch(
        "/api/v1/auth/users/admin-1/role",
        json={"role": "fisherman"},
        headers=auth("admin-1"),
    )

    assert response.status_code == 200
    assert read_user(db, "admin-1")["role"] == "fisherman"


def test_a_role_change_takes_effect_on_the_next_request(
    client: TestClient,
) -> None:
    """
    The role is read from the database per request, never from the token, so a
    promotion applies without re-issuing credentials.
    """
    assert client.get("/api/v1/auth/me", headers=auth("fisher-1")).json()["role"] == "fisherman"

    client.patch(
        "/api/v1/auth/users/fisher-1/role",
        json={"role": "researcher"},
        headers=auth("admin-1"),
    )

    assert client.get("/api/v1/auth/me", headers=auth("fisher-1")).json()["role"] == "researcher"


# ─────────────────────────────────────────────────────────────────────────────
# Brute-force defences
# ─────────────────────────────────────────────────────────────────────────────
def test_registration_is_rate_limited(client: TestClient) -> None:
    """
    Without a cap, the signup endpoint is a free account-creation and
    email-enumeration engine.
    """
    statuses = [
        client.post(
            "/api/v1/auth/register",
            json={
                "email": f"flood{i}@example.com",
                "password": "adequate1password",
                "name": f"Flood {i}",
            },
        ).status_code
        for i in range(8)
    ]

    assert 429 in statuses


def test_login_is_rate_limited(client: TestClient) -> None:
    """
    The password check is deliberately slow (600k PBKDF2 rounds), so an unbounded
    login endpoint is also a CPU exhaustion vector, not only a guessing oracle.
    """
    statuses = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "f@example.com", "password": f"guess-{i}"},
        ).status_code
        for i in range(14)
    ]

    assert 429 in statuses


def test_the_rate_limit_does_not_leak_whether_the_account_exists(
    client: TestClient,
) -> None:
    """
    Throttling must apply before the credential check, so a rejected attempt looks
    the same for a known and an unknown address.
    """
    unknown = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "guess1password"},
        ).status_code
        for _ in range(14)
    ]
    auth_router.limiter.reset()
    known = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "f@example.com", "password": "guess1password"},
        ).status_code
        for _ in range(14)
    ]

    assert unknown.count(429) == known.count(429)
