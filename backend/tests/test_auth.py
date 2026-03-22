from uuid import uuid4

from fastapi.testclient import TestClient


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Pytest Co",
            "email": f"pytest-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "api_key" in data
    return data


def test_auth_me_requires_token(client: TestClient):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_auth_me_returns_tenant_profile_for_valid_token(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["company_name"] == "Pytest Co"
    assert profile["email"].startswith("pytest-")
    assert len(profile["api_key_prefix"]) == 8
    assert profile["active_policy_version"] == 0
    assert "api_key" not in profile


def test_regenerate_key_invalidates_old_key_and_returns_new_raw_key(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]
    old_api_key = auth["api_key"]

    regenerate_response = client.post(
        "/api/v1/auth/regenerate-key",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert regenerate_response.status_code == 200
    regenerated = regenerate_response.json()
    new_api_key = regenerated["api_key"]
    assert new_api_key != old_api_key
    assert len(new_api_key) == 64
    assert len(regenerated["api_key_prefix"]) == 8

    old_key_response = client.post(
        "/api/v1/hooks/sanitize",
        headers={"X-API-Key": old_api_key},
        json={"message": "safe text", "session_id": "old-key"},
    )
    assert old_key_response.status_code == 401

    new_key_response = client.post(
        "/api/v1/hooks/sanitize",
        headers={"X-API-Key": new_api_key},
        json={"message": "safe text", "session_id": "new-key"},
    )
    assert new_key_response.status_code == 200


def test_tenant_cannot_access_another_tenant_profile(client: TestClient):
    tenant_a = _signup(client, str(uuid4()))
    tenant_b = _signup(client, str(uuid4()))

    profile_a = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tenant_a['access_token']}"},
    )
    profile_b = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tenant_b['access_token']}"},
    )

    assert profile_a.status_code == 200
    assert profile_b.status_code == 200
    assert profile_a.json()["id"] != profile_b.json()["id"]
    assert profile_a.json()["email"] != profile_b.json()["email"]
