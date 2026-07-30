"""
FishDex AI Server - Local user authentication
=============================================
Email/password registration and login backed by the local SQLite database.

Security properties
-------------------
* Session tokens are HMAC-signed and expiring (see :mod:`app.security`).
  They cannot be forged client-side.
* The ``role`` is **never** accepted from the client. New accounts are always
  created as ``fisherman``; elevation is an administrative operation.
* Password comparison is constant-time; hashes use PBKDF2-HMAC-SHA256.
* Registration and login are rate-limited and return non-enumerable errors.
"""

# NOTE: `from __future__ import annotations` is deliberately NOT used here.
# slowapi's @limiter.limit wrapper does not carry over the decorated function's
# __globals__, so FastAPI cannot resolve stringified forward references such as
# "RegisterRequest" and raises PydanticUndefinedAnnotation at import time.

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import db_session, get_db_connection
from app.security import (
    create_session_token,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
    verify_session_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address)

# Roles a user may hold. Only an administrator can grant anything above
# ``fisherman``; see ``PATCH /api/v1/auth/users/{user_id}/role``.
DEFAULT_ROLE = "fisherman"
ELEVATED_ROLES = frozenset({"researcher", "admin"})
ASSIGNABLE_ROLES = frozenset({DEFAULT_ROLE}) | ELEVATED_ROLES

# Deliberately identical message for "unknown email" and "wrong password" so the
# endpoint cannot be used to enumerate registered accounts.
_INVALID_CREDENTIALS_DETAIL = "Correo o contraseña incorrectos"


# ─── Request/response models ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Payload for creating a new local account."""

    email: EmailStr
    password: str = Field(..., min_length=10, max_length=1024)
    name: str = Field(..., min_length=1, max_length=120)


class LoginRequest(BaseModel):
    """Payload for exchanging credentials for a session token."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=1024)


class UserResponse(BaseModel):
    """Public representation of a user account."""

    id: str
    email: str
    name: str
    role: str


class LoginResponse(BaseModel):
    """Successful login result."""

    token: str
    user: UserResponse


class RoleUpdateRequest(BaseModel):
    """Administrative role change."""

    role: str = Field(..., description="One of: fisherman, researcher, admin")


# ─── Dependencies ───────────────────────────────────────────────────────────
def _extract_bearer_token(authorization: Optional[str]) -> str:
    """
    Pull the bearer token out of an Authorization header.

    Args:
        authorization: Raw header value, e.g. ``"Bearer abc.def"``.

    Returns:
        The token portion.

    Raises:
        HTTPException 401: Header missing or not a bearer scheme.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado Authorization",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Encabezado Authorization inválido",
        )
    return token.strip()


def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Resolve the authenticated user id from a signed session token.

    Args:
        authorization: ``Authorization: Bearer <token>`` header.

    Returns:
        The user id embedded in the verified token.

    Raises:
        HTTPException 401: Token missing, malformed, unsigned or expired.
    """
    token = _extract_bearer_token(authorization)
    payload = verify_session_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    return payload.user_id


def get_current_user(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict:
    """
    Load the authenticated user's authoritative record from the database.

    The role is always read from the database, never from the token or request
    body, so a stale or tampered client cannot elevate itself.

    Args:
        user_id: Verified user id.

    Returns:
        Dict with ``id``, ``email``, ``name`` and ``role``.

    Raises:
        HTTPException 401: The token is valid but the account no longer exists.
    """
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, email, name, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario autenticado no encontrado",
        )
    return dict(row)


def require_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    """
    Authorise administrator-only operations.

    Args:
        user: Authenticated user record.

    Returns:
        The same user record when it holds the ``admin`` role.

    Raises:
        HTTPException 403: The caller is not an administrator.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren privilegios de administrador",
        )
    return user


# ─── Endpoints ──────────────────────────────────────────────────────────────
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest) -> UserResponse:
    """
    Create a new local account with the default ``fisherman`` role.

    Args:
        request: Incoming request (required by the rate limiter).
        req: Validated registration payload.

    Returns:
        The created user.

    Raises:
        HTTPException 400: Password too weak.
        HTTPException 409: Email already registered.
        HTTPException 500: Unexpected persistence failure.
    """
    weakness = validate_password_strength(req.password)
    if weakness:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=weakness)

    email = req.email.strip().lower()
    user_id = str(uuid.uuid4())
    password_hash = hash_password(req.password)
    now = datetime.now(timezone.utc).isoformat()

    try:
        with db_session(commit=True) as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email, password_hash, req.name.strip(), DEFAULT_ROLE, now),
            )
            conn.execute(
                "INSERT INTO user_stats "
                "(id, user_id, total_xp, total_sightings, total_species, updated_at) "
                "VALUES (?, ?, 0, 0, 0, ?)",
                (str(uuid.uuid4()), user_id, now),
            )
    except sqlite3.IntegrityError:
        # UNIQUE(email) violation. 409 is unavoidable for a usable signup form,
        # but the message stays generic and the endpoint is rate-limited.
        logger.info("Registration rejected: email already in use")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo completar el registro con esos datos",
        )
    except sqlite3.Error as exc:
        logger.error("Failed to register user: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al registrar usuario",
        )

    logger.info("Registered new user %s with role %s", user_id, DEFAULT_ROLE)
    return UserResponse(id=user_id, email=email, name=req.name.strip(), role=DEFAULT_ROLE)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
def login(request: Request, req: LoginRequest) -> LoginResponse:
    """
    Exchange email/password credentials for a signed session token.

    Args:
        request: Incoming request (required by the rate limiter).
        req: Validated login payload.

    Returns:
        A session token plus the user record.

    Raises:
        HTTPException 401: Unknown email or wrong password (same message for both).
    """
    email = req.email.strip().lower()

    with db_session() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, name, role FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if row is None or not verify_password(req.password, row["password_hash"]):
        logger.info("Failed login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS_DETAIL,
        )

    _upgrade_hash_if_needed(row["id"], row["password_hash"], req.password)

    return LoginResponse(
        token=create_session_token(row["id"]),
        user=UserResponse(
            id=row["id"], email=row["email"], name=row["name"], role=row["role"]
        ),
    )


def _upgrade_hash_if_needed(user_id: str, stored_hash: str, password: str) -> None:
    """
    Transparently re-hash a password that used outdated parameters.

    Failures are logged and swallowed: a successful login must not be rejected
    because an opportunistic upgrade could not be persisted.

    Args:
        user_id: Owner of the hash.
        stored_hash: Hash currently in the database.
        password: Verified plain-text password.
    """
    if not needs_rehash(stored_hash):
        return
    try:
        with db_session(commit=True) as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user_id),
            )
        logger.info("Upgraded password hash parameters for user %s", user_id)
    except (sqlite3.Error, ValueError) as exc:
        logger.warning("Could not upgrade password hash for %s: %s", user_id, exc)


@router.get("/me", response_model=UserResponse)
def get_me(user: Annotated[dict, Depends(get_current_user)]) -> UserResponse:
    """
    Return the authenticated user's own profile.

    Args:
        user: Authenticated user record.

    Returns:
        The caller's account details.
    """
    return UserResponse(**user)


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: str,
    req: RoleUpdateRequest,
    admin: Annotated[dict, Depends(require_admin)],
) -> UserResponse:
    """
    Grant or revoke a role. Administrator-only.

    This replaces the previous behaviour where a client could self-assign any
    role at registration time.

    Args:
        user_id: Target account.
        req: Requested role.
        admin: Authenticated administrator (enforced by the dependency).

    Returns:
        The updated user record.

    Raises:
        HTTPException 400: Unknown role.
        HTTPException 404: Target user does not exist.
    """
    if req.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido. Permitidos: {sorted(ASSIGNABLE_ROLES)}",
        )

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE users SET role = ? WHERE id = ?", (req.role, user_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
            )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, name, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    except HTTPException:
        conn.rollback()
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        logger.error("Failed to update role for %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al actualizar el rol",
        )
    finally:
        conn.close()

    logger.info(
        "Admin %s changed role of user %s to %s", admin["id"], user_id, req.role
    )
    return UserResponse(**dict(row))
