"""
Tenant lifecycle integration tests — cross-cutting data integrity,
cascade deletes, uniqueness constraints, and session coherence.
"""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signup(client: TestClient, suffix: str = None, email: str = None) -> dict:
    suffix = suffix or str(uuid4())
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Lifecycle Co",
            "email": email or f"lifecycle-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _api_headers(api_key: str) -> dict:
    return {"X-API-Key": api_key}


async def _fake_embed(*_a, **_k) -> None:
    return None


def _fake_delay(*_a, **_k) -> None:
    return None


def _patch(monkeypatch) -> None:
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)


def _count_rows(table: str, where_col: str, where_val: str) -> int:
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {where_col} = :val"),
            {"val": where_val},
        )
        return result.scalar()


# ---------------------------------------------------------------------------
# 2G-1: Uniqueness constraints
# ---------------------------------------------------------------------------

def test_signup_unique_email_constraint(client: TestClient) -> None:
    """Two signups with the same email → second returns 409."""
    email = f"unique-{uuid4()}@example.com"
    first = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "First", "email": email, "password": "TestPass123!"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Second", "email": email, "password": "TestPass123!"},
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# 2G-2: Safety config created on signup
# ---------------------------------------------------------------------------

def test_safety_config_row_created_on_signup(client: TestClient) -> None:
    """After signup, the tenant's safety_config row exists in DB."""
    auth = _signup(client)
    me = client.get("/api/v1/auth/me", headers=_auth_headers(auth["access_token"]))
    tenant_id = me.json()["id"]

    count = _count_rows("safety_configs", "tenant_id", tenant_id)
    assert count == 1


# ---------------------------------------------------------------------------
# 2G-3: Policy embedding cascade delete
# ---------------------------------------------------------------------------

def test_policy_delete_removes_embeddings(client: TestClient, monkeypatch) -> None:
    """Deleting a policy removes its rows from policy_embeddings."""
    _patch(monkeypatch)
    auth = _signup(client)
    token = auth["access_token"]

    # Create a policy
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(token),
        json={
            "name": f"embed-cascade-{uuid4()}",
            "rule_text": "block this keyword",
            "rule_type": "keyword",
            "parameters": {"keyword": "block this keyword"},
        },
    )
    assert resp.status_code == 201
    policy_id = resp.json()["id"]

    # Delete the policy
    del_resp = client.delete(
        f"/api/v1/policies/{policy_id}",
        headers=_auth_headers(token),
    )
    assert del_resp.status_code == 204

    # Embeddings for the deleted policy should be cleaned up
    count = _count_rows("policy_embeddings", "policy_id", policy_id)
    assert count == 0


# ---------------------------------------------------------------------------
# 2G-4: API key cache invalidation after rotation
# ---------------------------------------------------------------------------

def test_api_key_cache_invalidated_after_regeneration(client: TestClient) -> None:
    """After key rotation, the old key is rejected even within cache TTL."""
    auth = _signup(client)
    old_key = auth["api_key"]
    token = auth["access_token"]

    # Old key works
    resp_before = client.post(
        "/api/v1/hooks/sanitize",
        headers=_api_headers(old_key),
        json={"message": "test before rotation"},
    )
    assert resp_before.status_code == 200

    # Rotate key
    regen = client.post("/api/v1/auth/regenerate-key", headers=_auth_headers(token))
    assert regen.status_code == 200
    new_key = regen.json()["api_key"]

    # Old key must fail immediately
    resp_after = client.post(
        "/api/v1/hooks/sanitize",
        headers=_api_headers(old_key),
        json={"message": "test after rotation"},
    )
    assert resp_after.status_code == 401

    # New key must work
    resp_new = client.post(
        "/api/v1/hooks/sanitize",
        headers=_api_headers(new_key),
        json={"message": "test new key"},
    )
    assert resp_new.status_code == 200


# ---------------------------------------------------------------------------
# 2G-5: Refresh token family revocation on password reset
# ---------------------------------------------------------------------------

def test_all_sessions_revoked_after_password_reset(client: TestClient) -> None:
    """After password reset, ALL existing refresh tokens for the tenant are revoked."""
    suffix = str(uuid4())
    email = f"lifecycle-reset-{suffix}@example.com"

    # Signup once
    auth = client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Reset Test Co", "email": email, "password": "TestPass123!"},
    ).json()

    # Login twice to get 2 separate refresh token families
    login1 = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass123!"}).json()
    login2 = client.post("/api/v1/auth/login", json={"email": email, "password": "TestPass123!"}).json()

    refresh1 = login1["refresh_token"]
    refresh2 = login2["refresh_token"]

    # Initiate password reset
    forgot_resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot_resp.status_code == 200
    reset_url = forgot_resp.json().get("reset_url")
    assert reset_url, "reset_url not returned in test environment"

    token = reset_url.split("token=")[1]
    reset_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewPass789!"},
    )
    assert reset_resp.status_code == 200

    # Both old refresh tokens must now fail
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh2}).status_code == 401


# ---------------------------------------------------------------------------
# 2G-6: Forgot-password email enumeration protection
# ---------------------------------------------------------------------------

def test_forgot_password_same_response_for_unknown_email(client: TestClient) -> None:
    """forgot-password returns 200 even for an email that doesn't exist."""
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody-registered-this@example.com"},
    )
    assert resp.status_code == 200
    assert "message" in resp.json()


def test_forgot_password_does_not_include_reset_url_for_unknown_email(client: TestClient) -> None:
    """reset_url is None when the email is not registered (no token generated)."""
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "definitely-not-registered@example.com"},
    )
    # reset_url should be None (or absent) since no tenant was found
    assert resp.json().get("reset_url") is None


# ---------------------------------------------------------------------------
# 2G-7: Reset password token is single-use
# ---------------------------------------------------------------------------

def test_reset_password_token_is_single_use(client: TestClient) -> None:
    """Reusing a consumed reset token → 400."""
    suffix = str(uuid4())
    email = f"lifecycle-single-use-{suffix}@example.com"

    client.post(
        "/api/v1/auth/signup",
        json={"company_name": "Single Use Co", "email": email, "password": "TestPass123!"},
    )

    forgot_resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    reset_url = forgot_resp.json().get("reset_url")
    assert reset_url

    token = reset_url.split("token=")[1]

    # First use — success
    first = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "FirstNewPass1!"},
    )
    assert first.status_code == 200

    # Second use — must fail (token consumed)
    second = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "SecondNewPass2!"},
    )
    assert second.status_code == 400
