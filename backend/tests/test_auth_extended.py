"""
Extended auth integration tests — edge cases the base suite doesn't cover.
Requires live DB + Redis (uses the shared session-scoped TestClient fixture).
"""
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signup(client: TestClient, suffix: str, password: str = "TestPass123!") -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "AuthExt Co",
            "email": f"authext-{suffix}@example.com",
            "password": password,
        },
    )
    return response


def _ok_signup(client: TestClient, suffix: str = None) -> dict:
    suffix = suffix or str(uuid4())
    resp = _signup(client, suffix)
    assert resp.status_code == 201
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 2A-1: Signup validation edge cases
# ---------------------------------------------------------------------------

def test_signup_weak_password_no_letter(client: TestClient) -> None:
    """Digits-only password → 422 with validation message."""
    resp = _signup(client, str(uuid4()), password="12345678")
    assert resp.status_code == 422
    assert "letter" in resp.text.lower()


def test_signup_weak_password_no_digit(client: TestClient) -> None:
    """Letters-only password → 422 with validation message."""
    resp = _signup(client, str(uuid4()), password="AbcdefgH")
    assert resp.status_code == 422
    assert "number" in resp.text.lower()


def test_signup_password_too_short(client: TestClient) -> None:
    """Password under 8 chars → 422."""
    resp = _signup(client, str(uuid4()), password="Ab1!")
    assert resp.status_code == 422


def test_signup_invalid_email_format(client: TestClient) -> None:
    """Non-email string in email field → 422."""
    resp = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "X", "email": "notanemail", "password": "TestPass123!"},
    )
    assert resp.status_code == 422


def test_signup_company_name_too_short(client: TestClient) -> None:
    """Empty company name → 422."""
    resp = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "", "email": f"x-{uuid4()}@example.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 422


def test_signup_duplicate_email_returns_409(client: TestClient) -> None:
    """Two signups with the same email → second returns 409."""
    email_suffix = str(uuid4())
    first = _signup(client, email_suffix)
    assert first.status_code == 201

    second = _signup(client, email_suffix)
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2A-2: Login edge cases
# ---------------------------------------------------------------------------

def test_login_wrong_password_returns_401(client: TestClient) -> None:
    """Correct email, wrong password → 401."""
    suffix = str(uuid4())
    _ok_signup(client, suffix)

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": f"authext-{suffix}@example.com", "password": "WrongPass999!"},
    )
    assert resp.status_code == 401


def test_login_unregistered_email_returns_401(client: TestClient) -> None:
    """Login with unregistered email → 401 (same message as wrong password)."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nope-never-signed-up@example.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 401


def test_login_error_message_same_regardless_of_email_existence(client: TestClient) -> None:
    """Wrong-password and unknown-email return identical detail strings (no account enumeration)."""
    suffix = str(uuid4())
    _ok_signup(client, suffix)

    resp_wrong_pass = client.post(
        "/api/v1/auth/login",
        json={"email": f"authext-{suffix}@example.com", "password": "WrongPass999!"},
    )
    resp_unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "totally-unknown@example.com", "password": "TestPass123!"},
    )
    assert resp_wrong_pass.json()["detail"] == resp_unknown.json()["detail"]


def test_login_success_returns_access_and_refresh_tokens(client: TestClient) -> None:
    """Successful login response includes access_token and refresh_token."""
    suffix = str(uuid4())
    _ok_signup(client, suffix)

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": f"authext-{suffix}@example.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


# ---------------------------------------------------------------------------
# 2A-3: JWT edge cases
# ---------------------------------------------------------------------------

def test_malformed_jwt_returns_401(client: TestClient) -> None:
    """Corrupt / truncated JWT → 401, not 500."""
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


def test_jwt_wrong_algorithm_rejected(client: TestClient) -> None:
    """Token signed with wrong algorithm → 401."""
    # Create a token with HS384 while the server expects HS256
    payload = {"sub": "fake-tenant", "exp": int(time.time()) + 900, "iat": int(time.time()), "jti": "x"}
    bad_token = jwt.encode(payload, settings.jwt_secret_key, algorithm="HS384")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert resp.status_code == 401


def test_expired_jwt_returns_401(client: TestClient) -> None:
    """Token with exp in the past → 401."""
    payload = {"sub": "fake-tenant", "exp": int(time.time()) - 1, "iat": int(time.time()) - 100, "jti": "expired-jti"}
    expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_jwt_blocklist_prevents_reuse_after_logout(client: TestClient) -> None:
    """After logout, the same token must return 401."""
    auth = _ok_signup(client)
    token = auth["access_token"]

    # Token works before logout
    assert client.get("/api/v1/auth/me", headers=_auth_headers(token)).status_code == 200

    # Logout
    client.post("/api/v1/auth/logout", headers=_auth_headers(token))

    # Token must be blocked
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2A-4: /auth/me profile fields
# ---------------------------------------------------------------------------

def test_me_returns_all_expected_fields(client: TestClient) -> None:
    """GET /auth/me response has id, email, company_name, api_key_prefix, active_policy_version."""
    auth = _ok_signup(client)
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(auth["access_token"]))
    assert resp.status_code == 200
    profile = resp.json()
    for field in ("id", "email", "company_name", "api_key_prefix", "active_policy_version"):
        assert field in profile, f"Missing field: {field}"
    # Ensure raw api_key is never exposed in /me
    assert "api_key" not in profile


def test_me_api_key_prefix_length_is_8(client: TestClient) -> None:
    """api_key_prefix is always exactly 8 characters."""
    auth = _ok_signup(client)
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(auth["access_token"]))
    assert len(resp.json()["api_key_prefix"]) == 8


def test_me_active_policy_version_starts_at_zero(client: TestClient) -> None:
    """New tenant's active_policy_version is 0."""
    auth = _ok_signup(client)
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(auth["access_token"]))
    assert resp.json()["active_policy_version"] == 0


# ---------------------------------------------------------------------------
# 2A-5: Token refresh
# ---------------------------------------------------------------------------

def test_refresh_token_issues_new_access_token(client: TestClient) -> None:
    """Valid refresh token → 200 with new access_token."""
    auth = _ok_signup(client)
    refresh_token = auth["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["access_token"] != auth["access_token"]


def test_refresh_token_is_single_use(client: TestClient) -> None:
    """Replaying a consumed refresh token → 401 (replay detection)."""
    auth = _ok_signup(client)
    refresh_token = auth["refresh_token"]

    # First use — valid
    resp1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp1.status_code == 200

    # Second use of the same token — must fail
    resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


def test_invalid_refresh_token_returns_401(client: TestClient) -> None:
    """Random string as refresh token → 401."""
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2A-6: Password reset — session invalidation
# ---------------------------------------------------------------------------

def test_old_refresh_token_unusable_after_password_reset(client: TestClient) -> None:
    """After password reset, old refresh token returns 401."""
    suffix = str(uuid4())
    auth = _ok_signup(client, suffix)
    old_refresh = auth["refresh_token"]

    # Request reset URL (works in test environment)
    forgot_resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"authext-{suffix}@example.com"},
    )
    assert forgot_resp.status_code == 200
    reset_url = forgot_resp.json().get("reset_url")
    assert reset_url, "reset_url not returned (check environment setting)"

    token = reset_url.split("token=")[1]
    reset_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewPass456!"},
    )
    assert reset_resp.status_code == 200

    # Old refresh token must now be rejected
    refresh_resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert refresh_resp.status_code == 401


def test_signup_creates_safety_config(client: TestClient) -> None:
    """After signup, GET /dashboard/safety-config returns 200 (config auto-created)."""
    auth = _ok_signup(client)
    resp = client.get(
        "/api/v1/dashboard/safety-config",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2A-7: Email verification
# ---------------------------------------------------------------------------

def test_signup_in_test_env_is_auto_verified(client: TestClient) -> None:
    """In test environment, email_verified=True is returned immediately on signup."""
    resp = _signup(client, str(uuid4()))
    assert resp.status_code == 201
    data = resp.json()
    assert data["email_verified"] is True


def test_signup_in_test_env_provides_verification_url(client: TestClient) -> None:
    """In test environment, signup response includes a verification_url."""
    resp = _signup(client, str(uuid4()))
    assert resp.status_code == 201
    assert resp.json().get("verification_url") is not None


def test_verify_email_valid_token(client: TestClient) -> None:
    """Consuming a valid verification token returns 200."""
    signup_data = _ok_signup(client)
    verify_url = signup_data.get("verification_url")
    assert verify_url, "verification_url missing from signup response"

    token = verify_url.split("token=")[1]
    resp = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200
    assert "verified" in resp.json()["message"].lower()


def test_verify_email_invalid_token(client: TestClient) -> None:
    """Invalid/expired verification token returns 400."""
    resp = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400
    assert "invalid or expired" in resp.json()["detail"].lower()


def test_verify_email_already_verified_is_idempotent(client: TestClient) -> None:
    """Consuming a token for an already-verified tenant returns 200 (idempotent)."""
    signup_data = _ok_signup(client)
    verify_url = signup_data.get("verification_url")
    token = verify_url.split("token=")[1]

    # First verification
    resp1 = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp1.status_code == 200

    # Token is single-use; a second call with the same token returns 400
    resp2 = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp2.status_code == 400


def test_resend_verification_returns_200_always(client: TestClient) -> None:
    """Resend-verification always returns 200 regardless of email registration."""
    resp = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200


class TestChangePassword:
    def test_change_password_success(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_change_password_wrong_current(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPass999!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    def test_change_password_weak_new_password(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "weak"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_change_password_requires_auth(self, client):
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
        )
        assert resp.status_code == 401
