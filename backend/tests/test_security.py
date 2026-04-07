"""
Security regression tests.

These tests verify that authorization boundaries, tenant isolation,
public endpoint exposure, and rate limiting all behave correctly.
They must pass on every PR — a failure here is a potential breach.
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

def _signup(client: TestClient, suffix: str = None) -> dict:
    suffix = suffix or str(uuid4())
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Security Test Co",
            "email": f"sec-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _api(key: str) -> dict:
    return {"X-API-Key": key}


async def _fake_embed(*_a, **_k) -> None:
    return None


def _fake_delay(*_a, **_k) -> None:
    return None


def _disable_all_checks(client: TestClient, token: str) -> None:
    client.put(
        "/api/v1/dashboard/safety-config",
        headers=_auth(token),
        json={
            "global_block_enabled": False,
            "injection_protection": False,
            "pii_redaction": False,
            "policy_enforcement": False,
        },
    )


# ---------------------------------------------------------------------------
# 3-1: Cross-tenant isolation — audit logs
# ---------------------------------------------------------------------------

def test_audit_logs_not_accessible_cross_tenant(client: TestClient) -> None:
    """Tenant B's JWT cannot see Tenant A's audit logs."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    # Tenant A produces a log
    _disable_all_checks(client, tenant_a["access_token"])
    client.post(
        "/api/v1/hooks/check",
        headers=_api(tenant_a["api_key"]),
        json={"message": "tenant a message"},
    )

    # Tenant B queries audit — must see NONE of A's logs
    logs_b = client.get(
        "/api/v1/audit/?limit=100",
        headers=_auth(tenant_b["access_token"]),
    )
    assert logs_b.status_code == 200
    tenant_a_id = client.get("/api/v1/auth/me", headers=_auth(tenant_a["access_token"])).json()["id"]
    returned_ids = {l["tenant_id"] for l in logs_b.json()["logs"]}
    assert tenant_a_id not in returned_ids


# ---------------------------------------------------------------------------
# 3-2: Cross-tenant isolation — policies
# ---------------------------------------------------------------------------

def test_policies_not_accessible_cross_tenant(client: TestClient, monkeypatch) -> None:
    """Tenant B cannot see Tenant A's policies."""
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)

    tenant_a = _signup(client)
    tenant_b = _signup(client)

    client.post(
        "/api/v1/policies/",
        headers=_auth(tenant_a["access_token"]),
        json={
            "name": f"secret-policy-{uuid4()}",
            "rule_text": "classified content",
            "rule_type": "keyword",
            "parameters": {"keyword": "classified content"},
        },
    )

    list_b = client.get("/api/v1/policies/", headers=_auth(tenant_b["access_token"]))
    assert list_b.status_code == 200
    names = [p["name"] for p in list_b.json()["policies"]]
    assert all("secret-policy" not in n for n in names)


def test_delete_other_tenants_policy_returns_404(client: TestClient, monkeypatch) -> None:
    """Tenant B cannot delete Tenant A's policy — returns 404, not 403."""
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)

    tenant_a = _signup(client)
    tenant_b = _signup(client)

    policy = client.post(
        "/api/v1/policies/",
        headers=_auth(tenant_a["access_token"]),
        json={
            "name": f"a-only-{uuid4()}",
            "rule_text": "test",
            "rule_type": "keyword",
            "parameters": {"keyword": "test"},
        },
    )
    assert policy.status_code == 201
    policy_id = policy.json()["id"]

    resp = client.delete(
        f"/api/v1/policies/{policy_id}",
        headers=_auth(tenant_b["access_token"]),
    )
    assert resp.status_code == 404


def test_update_other_tenants_policy_returns_404(client: TestClient, monkeypatch) -> None:
    """Tenant B cannot update Tenant A's policy."""
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)

    tenant_a = _signup(client)
    tenant_b = _signup(client)

    policy = client.post(
        "/api/v1/policies/",
        headers=_auth(tenant_a["access_token"]),
        json={
            "name": f"a-owned-{uuid4()}",
            "rule_text": "original rule",
            "rule_type": "keyword",
            "parameters": {"keyword": "original rule"},
        },
    )
    assert policy.status_code == 201
    policy_id = policy.json()["id"]

    resp = client.put(
        f"/api/v1/policies/{policy_id}",
        headers=_auth(tenant_b["access_token"]),
        json={"name": "Hijacked"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3-3: Cross-tenant isolation — dashboard
# ---------------------------------------------------------------------------

def test_dashboard_stats_are_tenant_scoped(client: TestClient) -> None:
    """Tenant B sees only their own stats, not Tenant A's."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    _disable_all_checks(client, tenant_a["access_token"])
    _disable_all_checks(client, tenant_b["access_token"])

    # Tenant A generates traffic
    for _ in range(3):
        client.post(
            "/api/v1/hooks/check",
            headers=_api(tenant_a["api_key"]),
            json={"message": "tenant a request"},
        )

    stats_b = client.get("/api/v1/dashboard/stats", headers=_auth(tenant_b["access_token"]))
    assert stats_b.status_code == 200
    # Tenant B's stats should not include Tenant A's 3 requests
    assert stats_b.json()["total_requests"] == 0


def test_safety_config_is_tenant_scoped(client: TestClient) -> None:
    """Tenant B cannot read or overwrite Tenant A's safety config."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    # Tenant A sets a distinctive fallback message
    client.put(
        "/api/v1/dashboard/safety-config",
        headers=_auth(tenant_a["access_token"]),
        json={"fallback_message": "secret-tenant-a-message"},
    )

    # Tenant B reads their own config — must NOT see Tenant A's message
    cfg_b = client.get("/api/v1/dashboard/safety-config", headers=_auth(tenant_b["access_token"]))
    assert cfg_b.status_code == 200
    assert cfg_b.json()["fallback_message"] != "secret-tenant-a-message"


# ---------------------------------------------------------------------------
# 3-4: API key cross-tenant isolation
# ---------------------------------------------------------------------------

def test_check_endpoint_wrong_api_key_is_401(client: TestClient) -> None:
    """Each API key authenticates its own tenant; a random key is rejected with 401."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    _disable_all_checks(client, tenant_a["access_token"])
    _disable_all_checks(client, tenant_b["access_token"])

    # Valid keys authenticate as their respective owners → 200
    resp_a = client.post(
        "/api/v1/hooks/check",
        headers={"X-API-Key": tenant_a["api_key"]},
        json={"message": "a's request"},
    )
    resp_b = client.post(
        "/api/v1/hooks/check",
        headers={"X-API-Key": tenant_b["api_key"]},
        json={"message": "b's request"},
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    # Audit IDs must differ — each call is logged under its own tenant
    assert resp_a.json()["audit_id"] != resp_b.json()["audit_id"]

    # Completely random key → 401
    bad = client.post(
        "/api/v1/hooks/check",
        headers={"X-API-Key": "deadbeef" * 8},
        json={"message": "unauthorized"},
    )
    assert bad.status_code == 401


def test_random_api_key_rejected(client: TestClient) -> None:
    """A completely random API key → 401."""
    resp = client.post(
        "/api/v1/hooks/check",
        headers={"X-API-Key": "a" * 64},
        json={"message": "unauthorized"},
    )
    assert resp.status_code == 401


def test_empty_api_key_rejected(client: TestClient) -> None:
    """Empty X-API-Key header value → 401."""
    resp = client.post(
        "/api/v1/hooks/check",
        headers={"X-API-Key": ""},
        json={"message": "test"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3-5: JWT forgery and manipulation
# ---------------------------------------------------------------------------

def test_jwt_with_manipulated_tenant_id_rejected(client: TestClient) -> None:
    """JWT signed with correct secret but wrong sub (non-existent tenant) → 401."""
    fake_payload = {
        "sub": str(uuid4()),   # tenant that doesn't exist
        "exp": int(time.time()) + 900,
        "iat": int(time.time()),
        "jti": "forged-jti",
    }
    forged_token = jwt.encode(
        fake_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    resp = client.get("/api/v1/auth/me", headers=_auth(forged_token))
    assert resp.status_code == 401


def test_jwt_signed_with_wrong_secret_rejected(client: TestClient) -> None:
    """Token signed with a different secret → 401."""
    payload = {
        "sub": "any-tenant",
        "exp": int(time.time()) + 900,
        "iat": int(time.time()),
        "jti": "wrong-secret",
    }
    bad_token = jwt.encode(payload, "wrong-secret-key", algorithm=settings.jwt_algorithm)
    resp = client.get("/api/v1/auth/me", headers=_auth(bad_token))
    assert resp.status_code == 401


def test_jwt_with_none_algorithm_rejected(client: TestClient) -> None:
    """Token claiming 'none' algorithm (unsigned) → 401."""
    # Build a raw token with alg=none — jose library won't sign it,
    # so we construct a forged unsigned token manually
    import base64, json as _json
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload_data = {"sub": "any", "exp": int(time.time()) + 900, "iat": int(time.time()), "jti": "none-alg"}
    payload_b64 = base64.urlsafe_b64encode(_json.dumps(payload_data).encode()).rstrip(b"=").decode()
    unsigned_token = f"{header}.{payload_b64}."

    resp = client.get("/api/v1/auth/me", headers=_auth(unsigned_token))
    assert resp.status_code == 401


def test_expired_token_rejected(client: TestClient) -> None:
    """Token with exp in the past → 401."""
    payload = {
        "sub": "tenant-x",
        "exp": int(time.time()) - 60,
        "iat": int(time.time()) - 120,
        "jti": "expired",
    }
    expired = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    resp = client.get("/api/v1/auth/me", headers=_auth(expired))
    assert resp.status_code == 401


def test_token_without_bearer_prefix_rejected(client: TestClient) -> None:
    """Authorization header without 'Bearer ' prefix → 401."""
    auth = _signup(client)
    token = auth["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": token})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3-6: Public vs protected endpoint exposure
# ---------------------------------------------------------------------------

def test_health_endpoint_is_public(client: TestClient) -> None:
    """GET /health → accessible with no auth header."""
    resp = client.get("/health")
    assert resp.status_code in (200, 503)  # may be 503 if models not loaded


def test_liveness_endpoint_is_public(client: TestClient) -> None:
    """GET /health/live → accessible with no auth header."""
    resp = client.get("/health/live")
    assert resp.status_code == 200


def test_validate_endpoint_requires_api_key(client: TestClient) -> None:
    """POST /validate without X-API-Key → 401."""
    resp = client.post("/api/v1/validate", json={"prompt": "hello"})
    assert resp.status_code == 401


def test_check_endpoint_requires_api_key(client: TestClient) -> None:
    """POST /hooks/check without X-API-Key → 401."""
    resp = client.post("/api/v1/hooks/check", json={"message": "hello"})
    assert resp.status_code == 401


def test_sanitize_endpoint_requires_api_key(client: TestClient) -> None:
    """POST /hooks/sanitize without X-API-Key → 401."""
    resp = client.post("/api/v1/hooks/sanitize", json={"message": "hello"})
    assert resp.status_code == 401


def test_audit_endpoint_requires_jwt(client: TestClient) -> None:
    """GET /audit/ without Authorization → 401."""
    resp = client.get("/api/v1/audit/")
    assert resp.status_code == 401


def test_dashboard_stats_requires_jwt(client: TestClient) -> None:
    """GET /dashboard/stats without Authorization → 401."""
    resp = client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 401


def test_policies_list_requires_jwt(client: TestClient) -> None:
    """GET /policies/ without Authorization → 401."""
    resp = client.get("/api/v1/policies/")
    assert resp.status_code == 401


def test_auth_login_requires_no_auth(client: TestClient) -> None:
    """POST /auth/login is publicly accessible (no auth header required)."""
    # Should return 401 for wrong creds, not 403/405
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "TestPass123!"},
    )
    assert resp.status_code == 401  # wrong creds, not an auth gate error


def test_auth_signup_requires_no_auth(client: TestClient) -> None:
    """POST /auth/signup is publicly accessible."""
    # Unique but intentionally invalid email format to check it reaches validation
    resp = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Test", "email": "not-an-email", "password": "TestPass123!"},
    )
    assert resp.status_code == 422  # reaches Pydantic validation, not an auth gate


# ---------------------------------------------------------------------------
# 3-7: Health check — no exception detail leakage
# ---------------------------------------------------------------------------

def test_health_response_never_exposes_internal_error_details(client: TestClient) -> None:
    """Health check body contains only 'healthy'/'degraded', not exception strings."""
    resp = client.get("/health")
    body_text = resp.text
    # Must not contain Python exception types or stack trace fragments
    for forbidden in ("Traceback", "Exception", "Error:", "line ", "File "):
        assert forbidden not in body_text, f"Response leaks internal detail: {forbidden!r}"


# ---------------------------------------------------------------------------
# 3-8: Rate limiting on sensitive endpoints
# ---------------------------------------------------------------------------

def test_rate_limit_on_signup(client: TestClient) -> None:
    """More than 5 signup attempts per minute → 429 on the 6th."""
    # Re-enable rate limiting just for this test
    from app.core.rate_limit import limiter
    limiter.enabled = True

    try:
        for i in range(5):
            client.post(
                "/api/v1/auth/signup",
                json={
                    "company_name": "RL Co",
                    "email": f"rl-signup-{uuid4()}@example.com",
                    "password": "TestPass123!",
                },
            )
        # 6th request — should be rate limited
        resp = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": "RL Co",
                "email": f"rl-signup-{uuid4()}@example.com",
                "password": "TestPass123!",
            },
        )
        assert resp.status_code == 429
    finally:
        limiter.enabled = False


def test_rate_limit_on_login(client: TestClient) -> None:
    """More than 10 login attempts per minute → 429 on the 11th."""
    from app.core.rate_limit import limiter
    limiter.enabled = True

    try:
        for i in range(10):
            client.post(
                "/api/v1/auth/login",
                json={"email": f"nobody-rl-{i}@example.com", "password": "TestPass123!"},
            )
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-rl-final@example.com", "password": "TestPass123!"},
        )
        assert resp.status_code == 429
    finally:
        limiter.enabled = False


def test_rate_limit_on_forgot_password(client: TestClient) -> None:
    """More than 5 forgot-password requests per minute → 429 on the 6th."""
    from app.core.rate_limit import limiter
    limiter.enabled = True

    try:
        for _ in range(5):
            client.post("/api/v1/auth/forgot-password", json={"email": "anybody@example.com"})
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "anybody@example.com"})
        assert resp.status_code == 429
    finally:
        limiter.enabled = False


# ---------------------------------------------------------------------------
# 3-9: Input sanitization — XSS via policy name
# ---------------------------------------------------------------------------

def test_policy_name_html_tags_stripped(client: TestClient, monkeypatch) -> None:
    """HTML/script tags in policy name are stripped before storage (XSS prevention)."""
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)

    auth = _signup(client)
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth(auth["access_token"]),
        json={
            "name": "<script>alert('xss')</script>My Policy",
            "rule_text": "safe",
            "rule_type": "keyword",
            "parameters": {"keyword": "safe"},
        },
    )
    assert resp.status_code == 201
    stored_name = resp.json()["name"]
    # HTML tags are stripped; text content may remain — the key safety guarantee
    # is that executable script tags are removed before storage
    assert "<script>" not in stored_name
    assert "</script>" not in stored_name


# ---------------------------------------------------------------------------
# 3-10: Logout token blocklist
# ---------------------------------------------------------------------------

def test_logged_out_token_cannot_access_protected_endpoints(client: TestClient) -> None:
    """After logout, the access token must be blocked on all protected endpoints."""
    auth = _signup(client)
    token = auth["access_token"]

    # Works before logout
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 200
    assert client.get("/api/v1/audit/", headers=_auth(token)).status_code == 200

    # Logout
    client.post("/api/v1/auth/logout", headers=_auth(token))

    # Both endpoints must reject the revoked token
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 401
    assert client.get("/api/v1/audit/", headers=_auth(token)).status_code == 401
    assert client.get("/api/v1/dashboard/stats", headers=_auth(token)).status_code == 401
