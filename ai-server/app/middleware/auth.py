"""
FishDex AI Server - Shared-secret authentication middleware
===========================================================
Validates machine-to-machine requests using either:

* ``X-FishDex-Client-Secret`` — the shared secret bundled with the mobile app;
* ``Authorization: Bearer <server_secret>`` — the server-to-server secret;
* ``Authorization: Bearer <session_token>`` — a signed per-user session token
  issued by ``/api/v1/auth/login``.

All secret comparisons are constant-time to avoid leaking the secret through
response timing.

Note on trust levels
--------------------
A shared client secret identifies the *application*, not a user: every install
carries the same value, so it must never be used on its own to authorise access
to another user's data. Endpoints that return per-user data must depend on
:func:`app.routers.auth.get_current_user` instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.security import constant_time_compare, verify_session_token

logger = logging.getLogger(__name__)

# ─── Bearer token extractor ─────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)

CLIENT_SECRET_HEADER = "X-FishDex-Client-Secret"


# ─── Authenticated principal ────────────────────────────────────────────
@dataclass(frozen=True)
class AuthenticatedUser:
    """
    Represents the caller of a request.

    Attributes:
        user_id: Stable identifier. For shared-secret callers this is a
            synthetic value (``"client-auth"`` / ``"server-auth"``) and must
            NOT be treated as a real user identity.
        email: Email address when known, otherwise empty.
        name: Display name.
        is_machine: True when authenticated with a shared secret rather than a
            per-user session token. Endpoints returning personal data should
            reject machine principals.
    """

    user_id: str
    email: str
    name: str
    is_machine: bool = False


async def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates authentication.

    Resolution order: dev bypass, per-user session token, server secret,
    client secret.

    Args:
        request: Incoming request, used to read the client-secret header.
        credentials: Parsed bearer credentials, if any.

    Returns:
        The authenticated principal.

    Raises:
        HTTPException 401: No valid credential was supplied.
    """
    # ── Dev bypass ──────────────────────────────────────────────────
    if settings.skip_auth:
        logger.debug("SKIP_AUTH enabled — returning dev user")
        return AuthenticatedUser(
            user_id="dev-user-000",
            email="dev@fishdex.local",
            name="Dev User",
        )

    # ── Per-user session token (strongest: identifies a real account) ──
    if credentials is not None:
        payload = verify_session_token(credentials.credentials)
        if payload is not None:
            return AuthenticatedUser(
                user_id=payload.user_id,
                email="",
                name="Session User",
                is_machine=False,
            )

        # ── Server-to-server shared secret ──────────────────────────
        if constant_time_compare(credentials.credentials, settings.ai_server_secret):
            return AuthenticatedUser(
                user_id="server-auth",
                email="",
                name="Server Auth",
                is_machine=True,
            )

    # ── Application-wide client secret ──────────────────────────────
    client_secret = request.headers.get(CLIENT_SECRET_HEADER)
    if constant_time_compare(client_secret, settings.client_secret):
        return AuthenticatedUser(
            user_id="client-auth",
            email="",
            name="Client Auth",
            is_machine=True,
        )

    # ── No valid auth ───────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Missing or invalid authentication. Provide a session token, "
            f"a Bearer server secret, or the {CLIENT_SECRET_HEADER} header."
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_machine_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    Dependency for endpoints that only need to prove the caller is a known
    client or the server itself (no per-user data involved).

    Args:
        request: Incoming request.
        credentials: Parsed bearer credentials, if any.

    Returns:
        The authenticated principal.

    Raises:
        HTTPException 401: No valid credential was supplied.
    """
    return await verify_auth(request, credentials)
