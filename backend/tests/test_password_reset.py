"""Tests for the password-reset flow (forgot-password + reset-password)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Reset Test Co",
            "email": f"reset-{suffix}@example.com",
            "password": "OldPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, email: str, password: str) -> int:
    """Return the HTTP status code of a login attempt."""
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    ).status_code


# ---------------------------------------------------------------------------
# forgot-password
# ---------------------------------------------------------------------------


def test_forgot_password_returns_200_for_registered_email(client: TestClient):
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    response = client.post("/api/v1/auth/forgot-password", json={"email": email})

    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_forgot_password_returns_200_for_unknown_email(client: TestClient):
    """Should not reveal whether an email is registered."""
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent-xyz@example.com"},
    )
    assert response.status_code == 200
    assert "message" in response.json()


def test_forgot_password_returns_reset_url_in_dev_mode(client: TestClient):
    """In development the reset_url is included so developers can action it."""
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    response = client.post("/api/v1/auth/forgot-password", json={"email": email})

    data = response.json()
    # reset_url is present in development (settings.environment == "development")
    assert data.get("reset_url") is not None
    assert "/reset-password?token=" in data["reset_url"]


# ---------------------------------------------------------------------------
# reset-password
# ---------------------------------------------------------------------------


def _get_reset_token(client: TestClient, email: str) -> str:
    """Helper: request a reset and extract the token from the dev reset_url."""
    response = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    reset_url: str = response.json()["reset_url"]
    return reset_url.split("token=")[-1]


def test_reset_password_succeeds_with_valid_token(client: TestClient):
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    token = _get_reset_token(client, email)
    new_password = "NewPass456!"

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )

    assert response.status_code == 200
    assert "message" in response.json()


def test_reset_password_allows_login_with_new_password(client: TestClient):
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    token = _get_reset_token(client, email)
    new_password = "BrandNew789!"

    client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )

    # Old password should no longer work.
    assert _login(client, email, "OldPass123!") == 401
    # New password should work.
    assert _login(client, email, new_password) == 200


def test_reset_password_token_is_single_use(client: TestClient):
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    token = _get_reset_token(client, email)

    first = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "FirstReset1!"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "SecondReset2!"},
    )
    assert second.status_code == 400
    assert "expired" in second.json()["detail"].lower() or "invalid" in second.json()["detail"].lower()


def test_reset_password_fails_with_invalid_token(client: TestClient):
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "completely-invalid-token-xyz", "new_password": "SomePass1!"},
    )
    assert response.status_code == 400


def test_reset_password_enforces_min_length(client: TestClient):
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    token = _get_reset_token(client, email)

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    # Pydantic validation rejects passwords shorter than 8 chars.
    assert response.status_code == 422


@pytest.mark.parametrize("new_password", ["ValidPass1!", "AnotherGood2@"])
def test_reset_password_full_flow(client: TestClient, new_password: str):
    """End-to-end: sign up → forgot password → reset → login with new password."""
    suffix = str(uuid4())
    email = f"reset-{suffix}@example.com"
    _signup(client, suffix)

    token = _get_reset_token(client, email)

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )
    assert reset_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": new_password},
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()
