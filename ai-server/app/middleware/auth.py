"""
FishDex AI Server - Authentication Middleware
===============================================
Validates requests using a shared secret (X-FishDex-Client-Secret header)
or a Bearer token matching the server secret.

In dev mode (SKIP_AUTH=True), all requests are accepted with a dummy user.
"""

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Bearer token extractor ─────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


# ─── Authenticated user model ───────────────────────────────────────────
@dataclass
class AuthenticatedUser:
    """Represents an authenticated user."""

    user_id: str
    email: str
    name: str


# ─── Auth verification dependency ───────────────────────────────────────
async def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates authentication.

    In dev mode (SKIP_AUTH=True), returns a dummy user.
    In production, validates the Bearer token or X-FishDex-Client-Secret header
    against the configured server secret.

    Raises:
        HTTPException 401: Missing or invalid credentials.
    """
    # ── Dev bypass ──────────────────────────────────────────────────
    if settings.skip_auth:
        logger.debug("SKIP_AUTH enabled — returning dev user")
        return AuthenticatedUser(
            user_id="dev-user-000",
            email="dev@fishdex.local",
            name="Dev User",
        )

    # ── Check X-FishDex-Client-Secret header first ──────────────────
    client_secret = request.headers.get("X-FishDex-Client-Secret")
    if client_secret and client_secret == settings.client_secret:
        # Extract user_id from the request body/form if available
        # For now, trust the user_id from the form data
        return AuthenticatedUser(
            user_id="client-auth",
            email="",
            name="Client Auth",
        )

    # ── Check Bearer token ──────────────────────────────────────────
    if credentials is not None:
        token = credentials.credentials
        if token == settings.ai_server_secret:
            return AuthenticatedUser(
                user_id="server-auth",
                email="",
                name="Server Auth",
            )

    # ── No valid auth ───────────────────────────────────────────────
    raise HTTPException(
        status_code=401,
        detail="Missing or invalid authentication. "
        "Provide X-FishDex-Client-Secret header or Bearer token.",
    )


# Keep backward-compatible alias
verify_appwrite_jwt = verify_auth
