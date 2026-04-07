"""
Extended policies integration tests — all rule types, update/delete lifecycle,
validation edge cases, pagination, and tenant isolation.
"""
from uuid import uuid4

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — mirrors pattern from existing test_policies.py
# ---------------------------------------------------------------------------

def _signup(client: TestClient, suffix: str = None) -> dict:
    suffix = suffix or str(uuid4())
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "PoliciesExt Co",
            "email": f"polext-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _fake_embed(*_args, **_kwargs) -> None:
    return None


def _fake_delay(*_args, **_kwargs) -> None:
    return None


def _patch(monkeypatch) -> None:
    from app.api.v1 import policies as policies_api
    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed)
    monkeypatch.setattr(policies_api.register_policy_on_chain_task, "delay", _fake_delay)


def _create_keyword_policy(client: TestClient, token: str, keyword: str = "forbidden", name: str = None) -> dict:
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(token),
        json={
            "name": name or f"kw-policy-{uuid4()}",
            "description": "Keyword block",
            "rule_text": keyword,
            "rule_type": "keyword",
            "parameters": {"keyword": keyword},
        },
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# 2C-1: Policy creation — all rule types
# ---------------------------------------------------------------------------

def test_create_keyword_policy_succeeds(client: TestClient, monkeypatch) -> None:
    """keyword rule_type → 201 with id."""
    _patch(monkeypatch)
    auth = _signup(client)
    policy = _create_keyword_policy(client, auth["access_token"])
    assert "id" in policy
    assert policy["rule_type"] == "keyword"


def test_create_regex_policy_succeeds(client: TestClient, monkeypatch) -> None:
    """regex_match rule_type with valid pattern → 201."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(auth["access_token"]),
        json={
            "name": f"regex-{uuid4()}",
            "description": "16-digit card blocker",
            "rule_text": "Block credit card numbers",
            "rule_type": "regex_match",
            "parameters": {"pattern": r"\d{16}"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rule_type"] == "regex_match"


def test_create_regex_policy_empty_pattern_returns_422(client: TestClient, monkeypatch) -> None:
    """regex_match with empty pattern string → 422 (schema requires non-empty)."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(auth["access_token"]),
        json={
            "name": f"empty-regex-{uuid4()}",
            "description": "Empty pattern",
            "rule_text": "test",
            "rule_type": "regex_match",
            "parameters": {"pattern": "   "},  # whitespace-only → fails validation
        },
    )
    assert resp.status_code == 422


def test_create_regex_policy_missing_pattern_returns_422(client: TestClient, monkeypatch) -> None:
    """regex_match without pattern in parameters → 422."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(auth["access_token"]),
        json={
            "name": f"no-pattern-{uuid4()}",
            "description": "No pattern field",
            "rule_text": "test",
            "rule_type": "regex_match",
            "parameters": {"wrong_field": "value"},
        },
    )
    assert resp.status_code == 422


def test_create_policy_name_max_length_255(client: TestClient, monkeypatch) -> None:
    """Name of exactly 255 chars → 201; 256 chars → 422."""
    _patch(monkeypatch)
    auth = _signup(client)

    # 255 chars — should succeed
    resp_ok = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(auth["access_token"]),
        json={
            "name": "A" * 255,
            "rule_text": "block this",
            "rule_type": "keyword",
            "parameters": {"keyword": "block this"},
        },
    )
    assert resp_ok.status_code == 201

    # 256 chars — should fail
    resp_fail = client.post(
        "/api/v1/policies/",
        headers=_auth_headers(auth["access_token"]),
        json={
            "name": "A" * 256,
            "rule_text": "block this",
            "rule_type": "keyword",
            "parameters": {"keyword": "block this"},
        },
    )
    assert resp_fail.status_code == 422


# ---------------------------------------------------------------------------
# 2C-2: Policy lifecycle — update and delete
# ---------------------------------------------------------------------------

def test_policy_update_changes_name(client: TestClient, monkeypatch) -> None:
    """PUT /policies/{id} → updated name reflected in GET."""
    _patch(monkeypatch)
    auth = _signup(client)
    policy = _create_keyword_policy(client, auth["access_token"])
    policy_id = policy["id"]

    update_resp = client.put(
        f"/api/v1/policies/{policy_id}",
        headers=_auth_headers(auth["access_token"]),
        json={"name": "Updated Name"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Name"


def test_policy_delete_removes_from_list(client: TestClient, monkeypatch) -> None:
    """Delete → policy no longer appears in list."""
    _patch(monkeypatch)
    auth = _signup(client)
    policy = _create_keyword_policy(client, auth["access_token"])
    policy_id = policy["id"]

    del_resp = client.delete(
        f"/api/v1/policies/{policy_id}",
        headers=_auth_headers(auth["access_token"]),
    )
    assert del_resp.status_code == 204

    list_resp = client.get("/api/v1/policies/", headers=_auth_headers(auth["access_token"]))
    ids = [p["id"] for p in list_resp.json()["policies"]]
    assert policy_id not in ids


def test_policy_delete_nonexistent_returns_404(client: TestClient, monkeypatch) -> None:
    """Delete a non-existent policy ID → 404."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.delete(
        f"/api/v1/policies/{uuid4()}",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 404


def test_policy_update_nonexistent_returns_404(client: TestClient, monkeypatch) -> None:
    """PUT on a non-existent policy ID → 404."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.put(
        f"/api/v1/policies/{uuid4()}",
        headers=_auth_headers(auth["access_token"]),
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2C-3: Enable/disable toggle
# ---------------------------------------------------------------------------

def test_disabled_policy_is_returned_in_list(client: TestClient, monkeypatch) -> None:
    """Disabled policy still appears in the list (just with is_enabled=False)."""
    _patch(monkeypatch)
    auth = _signup(client)
    policy = _create_keyword_policy(client, auth["access_token"])
    policy_id = policy["id"]

    # Disable it
    client.put(
        f"/api/v1/policies/{policy_id}",
        headers=_auth_headers(auth["access_token"]),
        json={"is_enabled": False},
    )

    list_resp = client.get("/api/v1/policies/", headers=_auth_headers(auth["access_token"]))
    policies = list_resp.json()["policies"]
    match = next((p for p in policies if p["id"] == policy_id), None)
    assert match is not None
    assert match["is_enabled"] is False


def test_enabled_policy_shows_is_enabled_true(client: TestClient, monkeypatch) -> None:
    """Newly created policy has is_enabled=True by default."""
    _patch(monkeypatch)
    auth = _signup(client)
    policy = _create_keyword_policy(client, auth["access_token"])
    assert policy["is_enabled"] is True


# ---------------------------------------------------------------------------
# 2C-4: Tenant isolation
# ---------------------------------------------------------------------------

def test_policy_list_is_tenant_isolated(client: TestClient, monkeypatch) -> None:
    """Tenant A's policies are not visible to Tenant B."""
    _patch(monkeypatch)
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    _create_keyword_policy(client, tenant_a["access_token"], keyword="secret-keyword-tenanta")

    list_b = client.get("/api/v1/policies/", headers=_auth_headers(tenant_b["access_token"]))
    assert list_b.status_code == 200
    names_b = [p["name"] for p in list_b.json()["policies"]]
    assert all("tenanta" not in n for n in names_b)


def test_policy_delete_cross_tenant_returns_404(client: TestClient, monkeypatch) -> None:
    """Tenant B cannot delete Tenant A's policy."""
    _patch(monkeypatch)
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    policy = _create_keyword_policy(client, tenant_a["access_token"])
    resp = client.delete(
        f"/api/v1/policies/{policy['id']}",
        headers=_auth_headers(tenant_b["access_token"]),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2C-5: Pagination
# ---------------------------------------------------------------------------

def test_policy_list_returns_policies_key(client: TestClient, monkeypatch) -> None:
    """GET /policies/ response has 'policies' array."""
    _patch(monkeypatch)
    auth = _signup(client)
    resp = client.get("/api/v1/policies/", headers=_auth_headers(auth["access_token"]))
    assert resp.status_code == 200
    assert "policies" in resp.json()


def test_policy_list_returns_all_tenant_policies(client: TestClient, monkeypatch) -> None:
    """Policy list endpoint returns all policies (no server-side pagination)."""
    _patch(monkeypatch)
    auth = _signup(client)
    # Create 3 policies — all should appear in list
    for i in range(3):
        _create_keyword_policy(client, auth["access_token"], keyword=f"unique-kw-{uuid4()}")

    resp = client.get("/api/v1/policies/", headers=_auth_headers(auth["access_token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert len(data["policies"]) >= 3


# ---------------------------------------------------------------------------
# 2C-6: Policy config version bump
# ---------------------------------------------------------------------------

def test_policy_config_update_bumps_version(client: TestClient) -> None:
    """PUT /policies/config → active_policy_version increments by 1."""
    auth = _signup(client)
    before_resp = client.get("/api/v1/policies/config", headers=_auth_headers(auth["access_token"]))
    assert before_resp.status_code == 200
    before_version = before_resp.json()["active_policy_version"]

    client.put(
        "/api/v1/policies/config",
        headers=_auth_headers(auth["access_token"]),
        json={"fail_mode": "open"},
    )

    after_resp = client.get("/api/v1/policies/config", headers=_auth_headers(auth["access_token"]))
    assert after_resp.json()["active_policy_version"] == before_version + 1


def test_policy_config_fail_mode_valid_values(client: TestClient) -> None:
    """fail_mode accepts 'open' and 'closed'; others → 422."""
    auth = _signup(client)

    for value in ("open", "closed"):
        resp = client.put(
            "/api/v1/policies/config",
            headers=_auth_headers(auth["access_token"]),
            json={"fail_mode": value},
        )
        assert resp.status_code == 200, f"Expected 200 for fail_mode={value}"

    bad_resp = client.put(
        "/api/v1/policies/config",
        headers=_auth_headers(auth["access_token"]),
        json={"fail_mode": "invalid_value"},
    )
    assert bad_resp.status_code == 422
