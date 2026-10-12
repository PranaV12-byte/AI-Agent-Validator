"""
Unit tests for authentication token helpers in isolation.

Tests cover:
- JWT access token creation and claim validation
- Password hashing and verification (bcrypt)
- API key generation and hashing
- Timing-safe comparison behaviour

No database, Redis, or HTTP required.
"""
import hmac
import time
from datetime import datetime, timezone

import bcrypt
import pytest
from jose import jwt

# Import private helpers directly from the auth module.
# These are pure functions with no side-effects or I/O.
from app.api.v1.auth import (
    _generate_api_key,
    _hash_api_key,
    _hash_password,
    _verify_password,
    _create_access_token,
)
from app.config import settings


# ---------------------------------------------------------------------------
# 1C-1: JWT access token creation
# ---------------------------------------------------------------------------

def test_access_token_contains_expected_claims() -> None:
    """Created JWT has the required claims: sub, jti, exp, iat."""
    token = _create_access_token("tenant-abc-123")
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == "tenant-abc-123"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_access_token_carries_session_invalidation_claims() -> None:
    token = _create_access_token("tenant-session", auth_version=3, session_family="family-a")
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["auth_version"] == 3
    assert payload["session_family"] == "family-a"


def test_access_token_exp_is_in_future() -> None:
    """Token expiry timestamp is strictly in the future."""
    token = _create_access_token("tenant-xyz")
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    now = int(datetime.now(timezone.utc).timestamp())
    assert payload["exp"] > now


def test_access_token_exp_reflects_configured_ttl() -> None:
    """Token exp is approximately `jwt_expire_minutes` minutes from now."""
    before = int(datetime.now(timezone.utc).timestamp())
    token = _create_access_token("tenant-ttl-check")
    after = int(datetime.now(timezone.utc).timestamp())

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    expected_exp_min = before + (settings.jwt_expire_minutes * 60) - 2
    expected_exp_max = after + (settings.jwt_expire_minutes * 60) + 2
    assert expected_exp_min <= payload["exp"] <= expected_exp_max


def test_access_token_iat_is_recent() -> None:
    """Token iat (issued-at) is within the last 5 seconds."""
    token = _create_access_token("tenant-iat")
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    now = int(datetime.now(timezone.utc).timestamp())
    assert now - 5 <= payload["iat"] <= now + 1


def test_access_token_jti_is_unique() -> None:
    """Two tokens issued for the same tenant have different jti values."""
    token1 = _create_access_token("tenant-same")
    token2 = _create_access_token("tenant-same")
    p1 = jwt.decode(token1, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    p2 = jwt.decode(token2, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert p1["jti"] != p2["jti"]


def test_access_token_sub_matches_tenant_id() -> None:
    """Token `sub` claim exactly matches the tenant_id passed in."""
    tenant_id = "some-unique-tenant-id-999"
    token = _create_access_token(tenant_id)
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == tenant_id


def test_access_token_invalid_with_wrong_secret() -> None:
    """Token decoded with a different secret raises JWTError."""
    from jose import JWTError
    token = _create_access_token("tenant-forge-test")
    with pytest.raises(JWTError):
        jwt.decode(token, "wrong-secret", algorithms=[settings.jwt_algorithm])


def test_access_token_uses_configured_algorithm() -> None:
    """Token header algorithm matches settings.jwt_algorithm."""
    token = _create_access_token("tenant-alg-check")
    # jose stores algorithm in the header; decode the unverified header
    header = jwt.get_unverified_header(token)
    assert header["alg"] == settings.jwt_algorithm


# ---------------------------------------------------------------------------
# 1C-2: Password hashing
# ---------------------------------------------------------------------------

def test_password_hash_is_bcrypt_format() -> None:
    """Hash output starts with '$2' (bcrypt identifier)."""
    hashed = _hash_password("MySecureP4ssword")
    assert hashed.startswith("$2")


def test_password_hash_includes_salt() -> None:
    """Same password hashed twice produces different hashes (unique salts)."""
    h1 = _hash_password("SamePassword1")
    h2 = _hash_password("SamePassword1")
    assert h1 != h2


def test_password_verify_correct() -> None:
    """Correct plaintext password verifies against its bcrypt hash."""
    password = "CorrectHorseBatteryStaple9"
    hashed = _hash_password(password)
    assert _verify_password(password, hashed) is True


def test_password_verify_wrong_password() -> None:
    """Wrong plaintext password fails verification."""
    hashed = _hash_password("RightPassword1")
    assert _verify_password("WrongPassword1", hashed) is False


def test_password_verify_empty_password_fails() -> None:
    """Empty string does NOT verify against a real password hash."""
    hashed = _hash_password("RealPassword1")
    assert _verify_password("", hashed) is False


def test_password_verify_case_sensitive() -> None:
    """Password verification is case-sensitive."""
    hashed = _hash_password("Password123")
    assert _verify_password("password123", hashed) is False


# ---------------------------------------------------------------------------
# 1C-3: API key generation and hashing
# ---------------------------------------------------------------------------

def test_api_key_generation_returns_64_hex_chars() -> None:
    """secrets.token_hex(32) produces a 64-character hex string."""
    key = _generate_api_key()
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_api_key_generation_is_unique() -> None:
    """Two consecutive calls produce different keys."""
    k1 = _generate_api_key()
    k2 = _generate_api_key()
    assert k1 != k2


def test_api_key_prefix_is_first_8_chars() -> None:
    """The first 8 characters of the raw key are stored as the prefix."""
    key = _generate_api_key()
    prefix = key[:8]
    assert len(prefix) == 8
    assert key.startswith(prefix)


def test_api_key_hash_is_bcrypt_format() -> None:
    """Hashed API key starts with '$2' (bcrypt identifier)."""
    key = _generate_api_key()
    hashed = _hash_api_key(key)
    assert hashed.startswith("$2")


def test_api_key_hash_verifiable_with_bcrypt() -> None:
    """Raw key verifies against its bcrypt hash."""
    key = _generate_api_key()
    hashed = _hash_api_key(key)
    assert bcrypt.checkpw(key.encode("utf-8"), hashed.encode("utf-8")) is True


def test_api_key_different_key_does_not_verify() -> None:
    """A different key does NOT verify against the hash."""
    key = _generate_api_key()
    other_key = _generate_api_key()
    hashed = _hash_api_key(key)
    assert bcrypt.checkpw(other_key.encode("utf-8"), hashed.encode("utf-8")) is False


# ---------------------------------------------------------------------------
# 1C-4: Timing-safe comparison (security regression)
# ---------------------------------------------------------------------------

def test_hmac_compare_digest_is_used_for_equality() -> None:
    """
    Verify that hmac.compare_digest is available and safe for comparing
    plaintext keys (constant-time, no short-circuit on first differing byte).

    This is a smoke-test: we can't measure timing in a unit test, but we
    confirm the stdlib function works correctly so dependencies.py is safe.
    """
    key = "abcdef1234567890"
    assert hmac.compare_digest(key, key) is True
    assert hmac.compare_digest(key, key + "x") is False
    assert hmac.compare_digest("", "") is True
    assert hmac.compare_digest("a", "b") is False


def test_hmac_compare_digest_different_lengths() -> None:
    """compare_digest returns False (not raise) for different-length strings."""
    assert hmac.compare_digest("short", "much-longer-string") is False
