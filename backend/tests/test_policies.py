from uuid import uuid4

from fastapi.testclient import TestClient


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Policy Pytest Co",
            "email": f"policy-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


async def _fake_embed_policy(*_args, **_kwargs) -> None:
    return None


def _fake_delay(*_args, **_kwargs) -> None:
    return None


def test_create_policy_rejects_invalid_parameters_schema(
    client: TestClient, monkeypatch
):
    from app.api.v1 import policies as policies_api

    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed_policy)
    monkeypatch.setattr(
        policies_api.register_policy_on_chain_task, "delay", _fake_delay
    )

    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]

    response = client.post(
        "/api/v1/policies/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Regex policy",
            "description": "Must include regex pattern",
            "rule_text": "Detect account numbers",
            "rule_type": "regex_match",
            "parameters": {"rubric": "Wrong field"},
        },
    )

    assert response.status_code == 422
    assert "parameters.pattern" in response.text


def test_delete_policy_removes_from_active_listing(client: TestClient, monkeypatch):
    from app.api.v1 import policies as policies_api

    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed_policy)
    monkeypatch.setattr(
        policies_api.register_policy_on_chain_task, "delay", _fake_delay
    )

    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]

    create_response = client.post(
        "/api/v1/policies/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Keyword policy",
            "description": "Block forbidden word",
            "rule_text": "forbidden",
            "rule_type": "keyword",
            "parameters": {"keyword": "forbidden"},
        },
    )
    assert create_response.status_code == 201
    policy_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    list_response = client.get(
        "/api/v1/policies/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200

    payload = list_response.json()
    ids = [policy["id"] for policy in payload["policies"]]
    assert policy_id not in ids


def test_policy_config_get_is_tenant_isolated(client: TestClient):
    tenant_a = _signup(client, str(uuid4()))
    tenant_b = _signup(client, str(uuid4()))

    token_a = tenant_a["access_token"]
    token_b = tenant_b["access_token"]

    update_b = client.put(
        "/api/v1/policies/config",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"fail_mode": "open"},
    )
    assert update_b.status_code == 200

    fetch_a = client.get(
        "/api/v1/policies/config",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert fetch_a.status_code == 200
    assert fetch_a.json()["fail_mode"] == "closed"


def test_policy_config_put_validates_payload_and_bumps_version(client: TestClient):
    tenant = _signup(client, str(uuid4()))
    token = tenant["access_token"]

    before = client.get(
        "/api/v1/policies/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before.status_code == 200
    before_version = before.json()["active_policy_version"]

    invalid = client.put(
        "/api/v1/policies/config",
        headers={"Authorization": f"Bearer {token}"},
        json={"fail_mode": "danger"},
    )
    assert invalid.status_code == 422

    updated = client.put(
        "/api/v1/policies/config",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "injection_protection": False,
            "pii_redaction": True,
            "fail_mode": "open",
            "fallback_message": "Flagged for review",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["active_policy_version"] == before_version + 1
    assert payload["injection_protection"] is False
    assert payload["fail_mode"] == "open"


def test_policy_update_and_delete_are_tenant_isolated(client: TestClient, monkeypatch):
    from app.api.v1 import policies as policies_api

    monkeypatch.setattr(policies_api.policy_engine, "embed_policy", _fake_embed_policy)
    monkeypatch.setattr(
        policies_api.register_policy_on_chain_task, "delay", _fake_delay
    )

    tenant_a = _signup(client, str(uuid4()))
    tenant_b = _signup(client, str(uuid4()))

    token_a = tenant_a["access_token"]
    token_b = tenant_b["access_token"]

    created = client.post(
        "/api/v1/policies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Tenant A Policy",
            "description": "owned by tenant A",
            "rule_text": "secret_pattern",
            "rule_type": "keyword",
            "parameters": {"keyword": "secret_pattern"},
        },
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    update_by_b = client.put(
        f"/api/v1/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Hijacked"},
    )
    assert update_by_b.status_code == 404

    delete_by_b = client.delete(
        f"/api/v1/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert delete_by_b.status_code == 404

    list_a = client.get(
        "/api/v1/policies/",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_a.status_code == 200
    ids = [policy["id"] for policy in list_a.json()["policies"]]
    assert policy_id in ids
