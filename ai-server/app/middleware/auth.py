"""
FishDex AI Server - Authentication Middleware
===============================================
Validates Appwrite JWT tokens by calling Appwrite's /account endpoint.
Provides a FastAPI dependency for protected routes.
"""

import logging
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Bearer token extractor ─────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


# ─── Authenticated user model ───────────────────────────────────────────
@dataclass
class AuthenticatedUser:
    """Represents a user whose JWT has been validated against Appwrite."""

    user_id: str
    email: str
    name: str


# ─── JWT verification dependency ────────────────────────────────────────
async def verify_appwrite_jwt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates an Appwrite JWT.

    In dev mode (SKIP_AUTH=True), returns a dummy user so the endpoint
    can be tested without a real token.

    For production, sends the JWT to Appwrite's GET /account endpoint
    with the X-Appwrite-JWT header. If Appwrite confirms the token,
    we return an AuthenticatedUser with the account details.

    Raises:
        HTTPException 401: Missing or invalid JWT.
        HTTPException 503: Appwrite service unreachable.
    """
    # ── Dev bypass ──────────────────────────────────────────────────
    if settings.skip_auth:
        logger.debug("SKIP_AUTH enabled — returning dev user")
        return AuthenticatedUser(
            user_id="dev-user-000",
            email="dev@fishdex.local",
            name="Dev User",
        )

    # ── Require token ───────────────────────────────────────────────
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token. Provide a Bearer JWT.",
        )

    jwt_token = credentials.credentials

    # ── Call Appwrite to validate ───────────────────────────────────
    appwrite_url = f"{settings.appwrite_endpoint}/v1/account"
    headers = {
        "Content-Type": "application/json",
        "X-Appwrite-Project": settings.appwrite_project_id,
        "X-Appwrite-JWT": jwt_token,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(appwrite_url, headers=headers)
    except httpx.ConnectError as exc:
        logger.error("Cannot reach Appwrite at %s: %s", appwrite_url, exc)
        raise HTTPException(
            status_code=503,
            detail="Authentication service is unreachable. Try again later.",
        )
    except httpx.TimeoutException:
        logger.error("Appwrite request timed out: %s", appwrite_url)
        raise HTTPException(
            status_code=503,
            detail="Authentication service timed out. Try again later.",
        )

    if resp.status_code != 200:
        logger.warning(
            "Appwrite JWT rejected (HTTP %d): %s", resp.status_code, resp.text[:200]
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        )

    # ── Parse Appwrite account response ────────────────────────────
    try:
        account = resp.json()
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Malformed response from authentication service.",
        )

    user_id = account.get("$id", "")
    email = account.get("email", "")
    name = account.get("name", "")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication succeeded but user ID is missing.",
        )

    logger.info("Authenticated user: %s (%s)", user_id, email)
    return AuthenticatedUser(user_id=user_id, email=email, name=name)
