"""
Extended health endpoint tests — liveness probe, response structure,
model readiness reporting, and error message safety.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 2F-1: Liveness probe
# ---------------------------------------------------------------------------

def test_liveness_always_returns_200(client: TestClient) -> None:
    """GET /health/live → 200 with {"status": "ok"} regardless of dependencies."""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_liveness_requires_no_auth(client: TestClient) -> None:
    """Liveness endpoint is publicly accessible (no auth header required)."""
    resp = client.get("/health/live")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2F-2: Deep health check response structure
# ---------------------------------------------------------------------------

def test_health_response_has_status_and_checks(client: TestClient) -> None:
    """GET /health response always has 'status' and 'checks' keys."""
    resp = client.get("/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert isinstance(body["checks"], dict)


def test_health_checks_contains_expected_keys(client: TestClient) -> None:
    """checks dict contains db, redis, model_injection, model_pii, model_policy."""
    resp = client.get("/health")
    checks = resp.json()["checks"]
    for key in ("db", "redis", "model_injection", "model_pii", "model_policy"):
        assert key in checks, f"Missing check key: {key}"


def test_health_check_values_are_valid_strings(client: TestClient) -> None:
    """Each check value is one of: 'ok', 'error', 'not_loaded'."""
    valid_values = {"ok", "error", "not_loaded"}
    resp = client.get("/health")
    for key, value in resp.json()["checks"].items():
        assert value in valid_values, f"Unexpected value '{value}' for check '{key}'"


def test_health_status_is_healthy_or_degraded(client: TestClient) -> None:
    """Top-level status is either 'healthy' or 'degraded', never a raw exception."""
    resp = client.get("/health")
    assert resp.json()["status"] in ("healthy", "degraded")


# ---------------------------------------------------------------------------
# 2F-3: 503 when dependencies are down
# ---------------------------------------------------------------------------

def test_health_503_when_db_unavailable(client: TestClient) -> None:
    """When DB raises an exception → response is 503, checks.db = 'error'."""
    from app.database import AsyncSessionLocal

    async def _broken_session():
        raise Exception("Connection refused")

    with patch("app.api.v1.health.AsyncSessionLocal") as mock_session_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["checks"]["db"] == "error"


def test_health_503_when_models_not_loaded(client: TestClient) -> None:
    """When ML models report not_ready → 503 with 'not_loaded' values."""
    with (
        patch("app.api.v1.health.injection_detector") as mock_inj,
        patch("app.api.v1.health.pii_redactor") as mock_pii,
        patch("app.api.v1.health.policy_engine") as mock_pol,
    ):
        mock_inj.is_ready = False
        mock_pii.is_ready = False
        mock_pol.is_ready = False

        resp = client.get("/health")

    assert resp.status_code == 503
    checks = resp.json()["checks"]
    assert checks["model_injection"] == "not_loaded"
    assert checks["model_pii"] == "not_loaded"
    assert checks["model_policy"] == "not_loaded"


# ---------------------------------------------------------------------------
# 2F-4: Error message safety (no exception detail leakage)
# ---------------------------------------------------------------------------

def test_health_no_exception_detail_in_response(client: TestClient) -> None:
    """When DB fails, response body must NOT contain raw exception message."""
    with patch("app.api.v1.health.AsyncSessionLocal") as mock_session_cls:
        error_msg = "SuperSecretInternalHostname:5432 connection refused"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception(error_msg))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        resp = client.get("/health")

    response_text = resp.text
    assert error_msg not in response_text
    assert "SuperSecretInternalHostname" not in response_text


def test_health_check_only_shows_ok_or_error_not_exception_type(client: TestClient) -> None:
    """checks.db must be the string 'error', not a Python exception repr."""
    with patch("app.api.v1.health.AsyncSessionLocal") as mock_session_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("some internal error"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_ctx

        resp = client.get("/health")

    checks = resp.json()["checks"]
    # Must be exactly "error", not "RuntimeError: some internal error" or similar
    assert checks["db"] == "error"
    assert "RuntimeError" not in checks["db"]
    assert "Exception" not in checks["db"]
