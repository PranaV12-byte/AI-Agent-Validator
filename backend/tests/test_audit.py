from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings


def _signup(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Audit Pytest Co",
            "email": f"audit-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )

    assert response.status_code == 201
    return response.json()


def _get_tenant_id(client: TestClient, token: str) -> UUID:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return UUID(response.json()["id"])


def _seed_audit_logs(tenant_id: UUID, total: int = 50) -> None:
    actions = ["BLOCKED", "ALLOWED", "REDACTED"]
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)

    insert_sql = text(
        """
        INSERT INTO audit_logs (
            id,
            tenant_id,
            session_id,
            hook_type,
            action,
            violation_type,
            severity,
            input_preview,
            details,
            payload_hash,
            processing_ms,
            ip_address,
            created_at
        ) VALUES (
            :id,
            :tenant_id,
            :session_id,
            :hook_type,
            :action,
            :violation_type,
            :severity,
            :input_preview,
            CAST(:details AS jsonb),
            :payload_hash,
            :processing_ms,
            CAST(:ip_address AS inet),
            :created_at
        )
        """
    )

    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        for index in range(total):
            action = actions[index % len(actions)]
            connection.execute(
                insert_sql,
                {
                    "id": str(uuid4()),
                    "tenant_id": str(tenant_id),
                    "session_id": f"seed-{index}",
                    "hook_type": "post_execution",
                    "action": action,
                    "violation_type": "prompt_injection"
                    if action == "BLOCKED"
                    else None,
                    "severity": "high" if action == "BLOCKED" else "low",
                    "input_preview": f"seed log {index}",
                    "details": f'{{"seeded": true, "index": {index}}}',
                    "payload_hash": f"hash-{index}",
                    "processing_ms": 20 + index,
                    "ip_address": None,
                    "created_at": now - timedelta(minutes=index),
                },
            )


def test_audit_endpoint_filters_by_action(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]
    tenant_id = _get_tenant_id(client, token)
    _seed_audit_logs(tenant_id, total=50)

    response = client.get(
        "/api/v1/audit/?action=BLOCKED&limit=100&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    logs = response.json()
    assert logs
    assert all(log["action"] == "BLOCKED" for log in logs)


def test_audit_endpoint_honors_limit(client: TestClient):
    auth = _signup(client, str(uuid4()))
    token = auth["access_token"]
    tenant_id = _get_tenant_id(client, token)
    _seed_audit_logs(tenant_id, total=50)

    response = client.get(
        "/api/v1/audit/?limit=10&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 10


def test_audit_endpoint_is_tenant_isolated(client: TestClient):
    tenant_a = _signup(client, str(uuid4()))
    tenant_b = _signup(client, str(uuid4()))

    token_a = tenant_a["access_token"]
    token_b = tenant_b["access_token"]

    tenant_a_id = _get_tenant_id(client, token_a)
    tenant_b_id = _get_tenant_id(client, token_b)

    _seed_audit_logs(tenant_a_id, total=6)
    _seed_audit_logs(tenant_b_id, total=4)

    logs_a = client.get(
        "/api/v1/audit/?limit=20&offset=0",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    logs_b = client.get(
        "/api/v1/audit/?limit=20&offset=0",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert logs_a.status_code == 200
    assert logs_b.status_code == 200
    assert len(logs_a.json()) >= 6
    assert len(logs_b.json()) >= 4

    ids_a = {entry["tenant_id"] for entry in logs_a.json()}
    ids_b = {entry["tenant_id"] for entry in logs_b.json()}
    assert str(tenant_a_id) in ids_a
    assert str(tenant_b_id) not in ids_a
    assert str(tenant_b_id) in ids_b
    assert str(tenant_a_id) not in ids_b
