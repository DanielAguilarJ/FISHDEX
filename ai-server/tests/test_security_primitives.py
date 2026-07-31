"""
Security primitives.

The session token replaced a scheme that was ``base64(user_id)`` with no
signature — anyone could mint a token for any account, including admin. What
matters now is that every way of *almost* having a valid token fails: a tampered
payload, a tampered signature, a token signed with a different secret, an expired
token, a structurally malformed one.

Password verification has to stay backward compatible with hashes written before
this module existed, while rejecting anything it does not recognise rather than
falling through to a permissive default.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest

from app.config import settings
from app.security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PBKDF2_ITERATIONS,
    TOKEN_TTL_SECONDS,
    constant_time_compare,
    create_session_token,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
    verify_session_token,
)


def legacy_hash(password: str, iterations: int = 100_000) -> str:
    """Reproduce the pre-audit ``salt_hex:key_hex`` hash format."""
    salt = b"\x01" * 16
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{salt.hex()}:{key.hex()}"


# ─────────────────────────────────────────────────────────────────────────────
# Constant-time comparison
# ─────────────────────────────────────────────────────────────────────────────
def test_identical_secrets_compare_equal() -> None:
    assert constant_time_compare("s3cret", "s3cret") is True


def test_different_secrets_compare_unequal() -> None:
    assert constant_time_compare("s3cret", "s3cr3t") is False


@pytest.mark.parametrize(
    ("left", "right"),
    [(None, "x"), ("x", None), (None, None), ("", "x"), ("x", ""), ("", "")],
)
def test_absent_or_empty_values_never_compare_equal(left, right) -> None:
    """
    An unset header must not authenticate against an unset secret. Two empty
    strings comparing equal would make a blank configuration accept blank
    credentials.
    """
    assert constant_time_compare(left, right) is False


def test_comparison_handles_non_ascii() -> None:
    assert constant_time_compare("contraseña", "contraseña") is True
    assert constant_time_compare("contraseña", "contrasena") is False


def test_comparison_is_length_sensitive() -> None:
    assert constant_time_compare("abc", "abcd") is False


# ─────────────────────────────────────────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────────────────────────────────────────
def test_hash_uses_the_configured_iteration_count() -> None:
    """
    OWASP 2023 recommends >= 600k for PBKDF2-HMAC-SHA256; the previous code used
    100k.
    """
    assert f"${PBKDF2_ITERATIONS}$" in hash_password("a valid password 1")
    assert PBKDF2_ITERATIONS >= 600_000


def test_hash_is_salted_per_password() -> None:
    """Equal passwords must not produce equal hashes, or the store is rainbow-able."""
    assert hash_password("same password 1") != hash_password("same password 1")


def test_hash_verifies_against_its_own_password() -> None:
    stored = hash_password("correct horse 7")

    assert verify_password("correct horse 7", stored) is True


def test_hash_rejects_a_different_password() -> None:
    stored = hash_password("correct horse 7")

    assert verify_password("wrong horse 7", stored) is False


def test_hash_rejects_an_empty_password() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_hash_rejects_an_oversized_password() -> None:
    """
    An unbounded input is a denial-of-service vector: PBKDF2 cost grows with the
    input, so a multi-megabyte 'password' would pin a worker.
    """
    with pytest.raises(ValueError):
        hash_password("x" * (MAX_PASSWORD_LENGTH + 1))


def test_verify_rejects_an_oversized_password_without_hashing() -> None:
    stored = hash_password("a valid password 1")

    assert verify_password("x" * (MAX_PASSWORD_LENGTH + 1), stored) is False


@pytest.mark.parametrize("blank", ["", None])
def test_verify_rejects_a_blank_password(blank) -> None:
    stored = hash_password("a valid password 1")

    assert verify_password(blank, stored) is False


@pytest.mark.parametrize("blank", ["", None])
def test_verify_rejects_a_blank_stored_hash(blank) -> None:
    assert verify_password("a valid password 1", blank) is False


# ─────────────────────────────────────────────────────────────────────────────
# Legacy hash compatibility
# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_hash_still_verifies() -> None:
    """Existing accounts must keep working after the upgrade."""
    assert verify_password("oldpassword", legacy_hash("oldpassword")) is True


def test_legacy_hash_rejects_a_wrong_password() -> None:
    assert verify_password("guess", legacy_hash("oldpassword")) is False


def test_legacy_hash_is_flagged_for_rehash() -> None:
    assert needs_rehash(legacy_hash("oldpassword")) is True


def test_current_hash_is_not_flagged_for_rehash() -> None:
    assert needs_rehash(hash_password("a valid password 1")) is False


def test_a_weaker_iteration_count_is_flagged_for_rehash() -> None:
    """A hash written with fewer rounds must be upgraded on next login."""
    weak = f"pbkdf2_sha256$1000${'ab' * 16}${'cd' * 32}"

    assert needs_rehash(weak) is True


@pytest.mark.parametrize(
    "malformed",
    [
        "not-a-hash",
        "pbkdf2_sha256$notanumber$aa$bb",
        "pbkdf2_sha256$600000$nothex$bb",
        "pbkdf2_sha256$600000",
        "::::",
        "zzzz:zzzz",
    ],
)
def test_a_malformed_hash_is_rejected_rather_than_crashing(malformed: str) -> None:
    """
    Fails closed. A parse error must not raise into the login handler, and must
    certainly not fall through to a permissive default.
    """
    assert verify_password("anything", malformed) is False


def test_an_unrecognised_hash_format_is_flagged_for_rehash() -> None:
    assert needs_rehash("bcrypt$something") is True


# ─────────────────────────────────────────────────────────────────────────────
# Session tokens — happy path
# ─────────────────────────────────────────────────────────────────────────────
def test_a_fresh_token_verifies() -> None:
    payload = verify_session_token(create_session_token("user-1"))

    assert payload is not None
    assert payload.user_id == "user-1"


def test_token_carries_issue_and_expiry_times() -> None:
    payload = verify_session_token(create_session_token("user-1"))

    assert payload is not None
    assert payload.expires_at > payload.issued_at


def test_default_ttl_is_applied() -> None:
    payload = verify_session_token(create_session_token("user-1"))

    assert payload is not None
    assert payload.expires_at - payload.issued_at == TOKEN_TTL_SECONDS


def test_a_custom_ttl_is_honoured() -> None:
    payload = verify_session_token(create_session_token("user-1", ttl_seconds=60))

    assert payload is not None
    assert payload.expires_at - payload.issued_at == 60


def test_token_creation_requires_a_user_id() -> None:
    with pytest.raises(ValueError):
        create_session_token("")


def test_tokens_for_different_users_differ() -> None:
    assert create_session_token("user-1") != create_session_token("user-2")


def test_a_user_id_with_unusual_characters_round_trips() -> None:
    """Ids are UUIDs today, but the encoding must not silently mangle anything."""
    user_id = "user/with:odd+chars=and.dots"

    payload = verify_session_token(create_session_token(user_id))

    assert payload is not None
    assert payload.user_id == user_id


# ─────────────────────────────────────────────────────────────────────────────
# Session tokens — every way of almost having one
# ─────────────────────────────────────────────────────────────────────────────
def test_the_old_unsigned_scheme_is_rejected() -> None:
    """base64(user_id), which is what the previous implementation issued."""
    assert verify_session_token(base64.b64encode(b"admin").decode()) is None


@pytest.mark.parametrize(
    "malformed",
    ["", "no-separator", ".", "..", "a.b.c.d", "!!!.???", "eyJ.", ".sig"],
)
def test_a_structurally_malformed_token_is_rejected(malformed: str) -> None:
    assert verify_session_token(malformed) is None


def test_none_is_rejected() -> None:
    assert verify_session_token(None) is None  # type: ignore[arg-type]


def test_a_tampered_signature_is_rejected() -> None:
    token = create_session_token("user-1")
    payload_part, _, signature = token.partition(".")

    tampered = f"{payload_part}.{'A' * len(signature)}"

    assert verify_session_token(tampered) is None


def test_a_tampered_payload_is_rejected() -> None:
    """
    The attack the signature exists to stop: swap the subject and keep the
    signature.
    """
    token = create_session_token("user-1")
    _, _, signature = token.partition(".")
    forged_payload = json.dumps(
        {"sub": "admin", "iat": int(time.time()), "exp": int(time.time()) + 999},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    forged = (
        base64.urlsafe_b64encode(forged_payload).decode().rstrip("=") + "." + signature
    )

    assert verify_session_token(forged) is None


def test_an_expired_token_is_rejected() -> None:
    expired = create_session_token("user-1", ttl_seconds=-1)

    assert verify_session_token(expired) is None


def test_a_token_expiring_exactly_now_is_rejected() -> None:
    """Boundary: exp <= now must not be accepted."""
    assert verify_session_token(create_session_token("user-1", ttl_seconds=0)) is None


def test_a_token_signed_with_another_secret_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Rotating the server secret must invalidate every outstanding session, which is
    the intended way to force a global logout.
    """
    token = create_session_token("user-1")
    monkeypatch.setattr(settings, "ai_server_secret", "a-completely-different-secret")

    assert verify_session_token(token) is None


def test_a_payload_missing_the_subject_is_rejected() -> None:
    """A validly signed token still needs a usable subject."""
    import hmac

    from app.security import _signing_key

    payload = json.dumps(
        {"iat": int(time.time()), "exp": int(time.time()) + 999},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(payload).decode().rstrip("=")
        + "."
        + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    )

    assert verify_session_token(token) is None


def test_a_payload_that_is_not_json_is_rejected() -> None:
    import hmac

    from app.security import _signing_key

    payload = b"this is not json"
    signature = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(payload).decode().rstrip("=")
        + "."
        + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    )

    assert verify_session_token(token) is None


def test_token_issuing_requires_a_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Refuses to mint an unsignable token rather than producing one anybody could
    forge.
    """
    monkeypatch.setattr(settings, "ai_server_secret", "")

    with pytest.raises(RuntimeError, match="must be configured"):
        create_session_token("user-1")


# ─────────────────────────────────────────────────────────────────────────────
# Password policy
# ─────────────────────────────────────────────────────────────────────────────
def test_a_compliant_password_is_accepted() -> None:
    assert validate_password_strength("abc123def456") is None


@pytest.mark.parametrize("short", ["", "a", "short", "123456789"])
def test_a_short_password_is_refused(short: str) -> None:
    assert len(short) < MIN_PASSWORD_LENGTH
    assert validate_password_strength(short) is not None


def test_an_all_numeric_password_is_refused() -> None:
    """The most common weak choice: a date or a phone number."""
    reason = validate_password_strength("1234567890123")

    assert reason is not None
    assert "letras" in reason


def test_an_all_alphabetic_password_is_refused() -> None:
    reason = validate_password_strength("abcdefghijklm")

    assert reason is not None
    assert "números" in reason


def test_an_oversized_password_is_refused() -> None:
    reason = validate_password_strength("a1" * MAX_PASSWORD_LENGTH)

    assert reason is not None
    assert "larga" in reason


def test_the_policy_message_states_the_minimum_length() -> None:
    """The user has to be told what to do, not just that they failed."""
    reason = validate_password_strength("abc")

    assert reason is not None
    assert str(MIN_PASSWORD_LENGTH) in reason


def test_a_passphrase_with_a_digit_is_accepted() -> None:
    assert validate_password_strength("correct horse battery 7") is None
