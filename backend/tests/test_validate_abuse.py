from uuid import uuid4

from fastapi.testclient import TestClient


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Abuse Pytest Co",
            "email": f"abuse-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }


def test_validate_rejects_prompt_over_max_length(client: TestClient):
    auth = _signup(client, str(uuid4()))
    response = client.post(
        "/api/v1/validate",
        headers=_auth_headers(auth["api_key"]),
        json={"prompt": "a" * 8001, "user_id": "abuse-long"},
    )

    assert response.status_code == 422


def test_validate_rejects_non_json_content_type(client: TestClient):
    auth = _signup(client, str(uuid4()))
    response = client.post(
        "/api/v1/validate",
        headers={"X-API-Key": auth["api_key"], "Content-Type": "text/plain"},
        content="prompt=hello",
    )

    assert response.status_code == 422


def test_validate_rejects_user_id_over_max_length(client: TestClient):
    auth = _signup(client, str(uuid4()))
    response = client.post(
        "/api/v1/validate",
        headers=_auth_headers(auth["api_key"]),
        json={"prompt": "hello", "user_id": "u" * 129},
    )

    assert response.status_code == 422


def test_validate_rejects_wrong_type_payload(client: TestClient):
    auth = _signup(client, str(uuid4()))
    response = client.post(
        "/api/v1/validate",
        headers=_auth_headers(auth["api_key"]),
        json={"prompt": {"text": "hello"}, "user_id": "abuse-type"},
    )

    assert response.status_code == 422


def test_validate_rejects_malformed_json(client: TestClient):
    auth = _signup(client, str(uuid4()))
    response = client.post(
        "/api/v1/validate",
        headers=_auth_headers(auth["api_key"]),
        content='{"prompt": "hello", "user_id": "broken",',
    )

    assert response.status_code == 422
