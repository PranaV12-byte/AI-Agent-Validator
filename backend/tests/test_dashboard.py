from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Dashboard Pytest Co",
            "email": f"dashboard-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_update_safety_config_rejects_negative_retention_days(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]

    response = client.put(
        "/api/v1/dashboard/safety-config",
        headers={"Authorization": f"Bearer {token}"},
        json={"log_retention_days": -1},
    )

    assert response.status_code == 422


def test_update_safety_config_persists_valid_payload(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]

    payload = {
        "global_block_enabled": True,
        "pii_redaction": False,
        "fallback_message": "Blocked by tenant policy.",
        "log_retention_days": 14,
    }

    update_response = client.put(
        "/api/v1/dashboard/safety-config",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["global_block_enabled"] is True
    assert updated["pii_redaction"] is False
    assert updated["fallback_message"] == "Blocked by tenant policy."
    assert updated["log_retention_days"] == 14

    fetch_response = client.get(
        "/api/v1/dashboard/safety-config",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert fetch_response.status_code == 200
    fetched = fetch_response.json()
    assert fetched["global_block_enabled"] is True
    assert fetched["log_retention_days"] == 14


def _seed_dashboard_log(tenant_id: str, action: str, processing_ms: int) -> None:
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)
    insert_sql = text(
        """
        INSERT INTO audit_logs (
            id,
            tenant_id,
            hook_type,
            action,
            severity,
            details,
            processing_ms,
            created_at
        ) VALUES (
            gen_random_uuid(),
            :tenant_id,
            'access',
            :action,
            'low',
            '{}'::jsonb,
            :processing_ms,
            NOW()
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            insert_sql,
            {
                "tenant_id": tenant_id,
                "action": action,
                "processing_ms": processing_ms,
            },
        )


def test_dashboard_stats_are_tenant_scoped(client: TestClient):
    tenant_a = _signup(client, str(uuid4()))
    tenant_b = _signup(client, str(uuid4()))

    token_a = tenant_a["access_token"]
    token_b = tenant_b["access_token"]

    me_a = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    me_b = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_a.status_code == 200
    assert me_b.status_code == 200

    tenant_a_id = me_a.json()["id"]
    tenant_b_id = me_b.json()["id"]

    _seed_dashboard_log(tenant_a_id, "BLOCKED", 100)
    _seed_dashboard_log(tenant_a_id, "ALLOWED", 200)
    _seed_dashboard_log(tenant_b_id, "ALLOWED", 300)

    stats_a = client.get(
        "/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {token_a}"}
    )
    stats_b = client.get(
        "/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {token_b}"}
    )

    assert stats_a.status_code == 200
    assert stats_b.status_code == 200

    payload_a = stats_a.json()
    payload_b = stats_b.json()

    assert payload_a["total_requests"] == 2
    assert payload_a["blocked_requests"] == 1
    assert payload_b["total_requests"] == 1
    assert payload_b["blocked_requests"] == 0
