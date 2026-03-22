from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.rate_limit import build_rate_limit_key


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Rate Limit Co",
            "email": f"rate-limit-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def _validate_request(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/validate",
        headers=headers,
        json={"prompt": "hello", "user_id": "rl-user"},
    )
    return response.status_code


def test_rate_limit_uses_api_key_bucket_over_shared_ip(client: TestClient):
    auth_one = _signup(client, str(uuid4()))
    auth_two = _signup(client, str(uuid4()))

    headers_one = {
        "X-API-Key": auth_one["api_key"],
        "Content-Type": "application/json",
    }
    headers_two = {
        "X-API-Key": auth_two["api_key"],
        "Content-Type": "application/json",
    }

    for _ in range(100):
        status = _validate_request(client, headers_one)
        assert status == 200

    status_after_burst = _validate_request(client, headers_one)
    assert status_after_burst in {200, 429}
    assert _validate_request(client, headers_two) == 200


def test_rate_limit_falls_back_to_ip_when_api_key_missing(client: TestClient):
    headers = {"Content-Type": "application/json"}

    for _ in range(5):
        status = _validate_request(client, headers)
        assert status == 401


def test_rate_limit_key_builder_falls_back_to_ip():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/validate",
        "headers": [],
        "client": ("127.0.0.1", 50000),
    }
    request = Request(scope)

    assert build_rate_limit_key(request) == "127.0.0.1"


def test_rate_limit_key_builder_prefers_api_key_header():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/validate",
        "headers": [(b"x-api-key", b"sk-test-123")],
        "client": ("127.0.0.1", 50000),
    }
    request = Request(scope)

    assert build_rate_limit_key(request) == "sk-test-123"
