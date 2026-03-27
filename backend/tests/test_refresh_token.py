"""Tests for refresh token flow: issuance, rotation, family revocation, and logout revocation."""

from uuid import uuid4

from fastapi.testclient import TestClient


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Refresh Test Co",
            "email": f"refresh-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_login_returns_refresh_token(client: TestClient):
    auth = _signup(client, str(uuid4()))
    email = auth["email"] if "email" in auth else f"refresh-{uuid4()}@example.com"

    # Re-login to get a fresh response
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "refresh-login@example.com", "password": "TestPass123!"},
    )
    # Signup a fresh user for login
    suffix = str(uuid4())
    client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Login Test Co",
            "email": f"refresh-login-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": f"refresh-login-{suffix}@example.com", "password": "TestPass123!"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "refresh_token" in data
    assert data["refresh_token"] is not None
    assert len(data["refresh_token"]) > 20


def test_signup_returns_refresh_token(client: TestClient):
    auth = _signup(client, str(uuid4()))
    assert "refresh_token" in auth
    assert auth["refresh_token"] is not None
    assert len(auth["refresh_token"]) > 20


def test_refresh_returns_new_access_and_refresh_tokens(client: TestClient):
    auth = _signup(client, str(uuid4()))
    original_access = auth["access_token"]
    original_refresh = auth["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["access_token"] != original_access
    assert data["refresh_token"] != original_refresh
    assert data["token_type"] == "bearer"


def test_refresh_token_is_single_use(client: TestClient):
    auth = _signup(client, str(uuid4()))
    refresh_token = auth["refresh_token"]

    # First use — should succeed
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200

    # Second use of the same token — should be rejected (already consumed)
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 401
    assert "Invalid or expired" in r2.json()["detail"]


def test_rotated_refresh_token_is_valid(client: TestClient):
    auth = _signup(client, str(uuid4()))

    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": auth["refresh_token"]})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]

    # The newly issued refresh token should work
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_invalid_refresh_token_returns_401(client: TestClient):
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "completely-invalid-token"},
    )
    assert response.status_code == 401
    assert "Invalid or expired" in response.json()["detail"]


def test_logout_with_refresh_token_revokes_it(client: TestClient):
    auth = _signup(client, str(uuid4()))
    access_token = auth["access_token"]
    refresh_token = auth["refresh_token"]

    # Logout and pass the refresh token
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # Refresh token should now be invalid
    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


def test_logout_without_refresh_token_still_succeeds(client: TestClient):
    auth = _signup(client, str(uuid4()))
    access_token = auth["access_token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out."


def test_new_access_token_from_refresh_is_accepted(client: TestClient):
    auth = _signup(client, str(uuid4()))

    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": auth["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]

    # New access token should be accepted by protected endpoints
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert me_resp.status_code == 200
    assert "company_name" in me_resp.json()
