"""
FishDex AI Server - Security primitives
=======================================
Password hashing, constant-time secret comparison and signed session tokens.

Why this module exists
---------------------
The previous session token was ``base64(user_id)`` with **no signature**, so
anybody could mint a token for an arbitrary user by base64-encoding their id.
Tokens issued here are HMAC-SHA256 signed and carry an expiry, so they cannot
be forged without the server secret.

The token format is deliberately simple (no external dependency):

    base64url(payload_json) + "." + base64url(hmac_sha256(payload_json))

``payload_json`` is ``{"sub": <user_id>, "iat": <issued_at>, "exp": <expires_at>}``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# ── Password hashing parameters ──────────────────────────────────────────────
# OWASP (2023) recommends >= 600_000 iterations for PBKDF2-HMAC-SHA256.
PBKDF2_ITERATIONS = 600_000
PBKDF2_ALGORITHM = "sha256"
_SALT_BYTES = 16

# Minimum password length enforced at the API boundary.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 1024  # Guard against DoS via multi-MB PBKDF2 input.

# ── Session token parameters ────────────────────────────────────────────────
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
_TOKEN_SEPARATOR = "."


# ─────────────────────────────────────────────────────────────────────────────
# Constant-time comparison
# ─────────────────────────────────────────────────────────────────────────────
def constant_time_compare(left: str | None, right: str | None) -> bool:
    """
    Compare two secrets without leaking their contents through timing.

    Args:
        left: First value (e.g. a client-supplied secret). May be None.
        right: Second value (e.g. the configured secret). May be None.

    Returns:
        True only when both values are non-empty and byte-identical.
    """
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """
    Derive a salted PBKDF2-HMAC-SHA256 hash for storage.

    Args:
        password: Plain-text password.

    Returns:
        A string of the form ``pbkdf2_sha256$<iterations>$<salt_hex>$<key_hex>``.

    Raises:
        ValueError: If the password is empty or exceeds the maximum length.
    """
    if not password:
        raise ValueError("password must not be empty")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("password exceeds maximum supported length")

    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    Verify a password against a stored hash, in constant time.

    Supports both the current ``pbkdf2_sha256$iterations$salt$key`` format and
    the legacy ``salt_hex:key_hex`` format (100 000 iterations) so that existing
    accounts keep working after the upgrade.

    Args:
        password: Plain-text password supplied by the client.
        stored: Hash previously produced by :func:`hash_password`.

    Returns:
        True when the password matches.
    """
    if not password or not stored:
        return False
    if len(password) > MAX_PASSWORD_LENGTH:
        return False

    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iterations_raw, salt_hex, key_hex = stored.split("$", 3)
            iterations = int(iterations_raw)
        elif ":" in stored:
            # Legacy format written before this module existed.
            salt_hex, key_hex = stored.split(":", 1)
            iterations = 100_000
        else:
            logger.warning("Unrecognised password hash format; rejecting login")
            return False

        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
    except (ValueError, TypeError):
        logger.warning("Malformed password hash in database; rejecting login")
        return False

    candidate = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM, password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """
    Report whether a stored hash uses outdated parameters.

    Args:
        stored: Hash from the database.

    Returns:
        True when the hash should be upgraded on the next successful login.
    """
    if not stored.startswith("pbkdf2_sha256$"):
        return True
    try:
        iterations = int(stored.split("$", 3)[1])
    except (ValueError, IndexError):
        return True
    return iterations < PBKDF2_ITERATIONS


# ─────────────────────────────────────────────────────────────────────────────
# Signed session tokens
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TokenPayload:
    """Decoded contents of a valid session token."""

    user_id: str
    issued_at: int
    expires_at: int


def _b64url_encode(raw: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    """Base64url-decode a value that may be missing its padding."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signing_key() -> bytes:
    """
    Return the HMAC signing key derived from the configured server secret.

    Raises:
        RuntimeError: If no usable secret is configured.
    """
    secret = settings.ai_server_secret
    if not secret:
        raise RuntimeError("FISHDEX_AI_SERVER_SECRET must be configured to issue tokens")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def create_session_token(user_id: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    """
    Issue a signed, expiring session token for ``user_id``.

    Args:
        user_id: Identifier to embed in the token subject.
        ttl_seconds: Lifetime of the token in seconds.

    Returns:
        The encoded token string.

    Raises:
        ValueError: If ``user_id`` is empty.
    """
    if not user_id:
        raise ValueError("user_id must not be empty")

    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(_signing_key(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}{_TOKEN_SEPARATOR}{_b64url_encode(signature)}"


def verify_session_token(token: str) -> TokenPayload | None:
    """
    Validate a session token's signature and expiry.

    Args:
        token: Token previously produced by :func:`create_session_token`.

    Returns:
        The decoded :class:`TokenPayload`, or None when the token is malformed,
        has an invalid signature, or has expired.
    """
    if not token or _TOKEN_SEPARATOR not in token:
        return None

    encoded_payload, _, encoded_signature = token.partition(_TOKEN_SEPARATOR)
    try:
        payload_bytes = _b64url_decode(encoded_payload)
        provided_signature = _b64url_decode(encoded_signature)
    except (ValueError, TypeError):
        return None

    expected_signature = hmac.new(_signing_key(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        logger.warning("Rejected session token with invalid signature")
        return None

    try:
        payload = json.loads(payload_bytes)
        user_id = str(payload["sub"])
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
    except (ValueError, TypeError, KeyError):
        logger.warning("Rejected session token with malformed payload")
        return None

    if not user_id:
        return None
    if expires_at <= int(time.time()):
        logger.info("Rejected expired session token for user %s", user_id)
        return None

    return TokenPayload(user_id=user_id, issued_at=issued_at, expires_at=expires_at)


def validate_password_strength(password: str) -> str | None:
    """
    Check a password against the minimum policy.

    Args:
        password: Candidate password.

    Returns:
        None when acceptable, otherwise a human-readable reason in Spanish
        (the API's user-facing language).
    """
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
    if len(password) > MAX_PASSWORD_LENGTH:
        return "La contraseña es demasiado larga"
    if password.isdigit() or password.isalpha():
        return "La contraseña debe combinar letras y números"
    return None
