from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.main import app as fastapi_app
from app.core.rate_limit import limiter


@pytest.fixture(scope="session")
def app() -> FastAPI:
    @asynccontextmanager
    async def noop_lifespan(_: FastAPI):
        yield

    fastapi_app.router.lifespan_context = noop_lifespan
    # Disable rate limiting for the test session so tests don't interfere
    # with each other's per-IP counters (all share 127.0.0.1).
    limiter.enabled = False
    return fastapi_app


@pytest.fixture(scope="session")
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Shared factory fixtures (Phase 7A)
# ---------------------------------------------------------------------------

@pytest.fixture
def make_tenant(client: TestClient):
    """Return a callable that creates a new tenant and returns its auth data.

    Usage::

        def test_foo(make_tenant):
            data = make_tenant()          # auto-generated suffix
            data = make_tenant("alice")   # deterministic suffix
    """
    def _make(suffix: str | None = None, password: str = "TestPass123!") -> dict:
        suffix = suffix or str(uuid4())
        resp = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": f"Co-{suffix}",
                "email": f"tenant-{suffix}@example.com",
                "password": password,
            },
        )
        # Avoid printing resp.text in the assertion message — signup responses
        # include api_key which would appear in CI logs on failure.
        assert resp.status_code == 201, f"Signup failed with status {resp.status_code}"
        return resp.json()

    return _make


@pytest.fixture
def auth_headers(make_tenant):
    """Return a callable that creates a tenant and returns JWT auth headers.

    Usage::

        def test_foo(auth_headers):
            headers = auth_headers()
    """
    def _make(suffix: str | None = None) -> dict:
        data = make_tenant(suffix)
        return {"Authorization": f"Bearer {data['access_token']}"}

    return _make


@pytest.fixture
def api_headers(make_tenant):
    """Return a callable that creates a tenant and returns API-key headers.

    Usage::

        def test_foo(api_headers):
            headers = api_headers()
    """
    def _make(suffix: str | None = None) -> dict:
        data = make_tenant(suffix)
        return {"X-API-Key": data["api_key"]}

    return _make


@pytest.fixture
def make_policy(client: TestClient):
    """Return a callable that creates a policy for the given tenant.

    Usage::

        def test_foo(make_tenant, make_policy):
            tenant = make_tenant()
            headers = {"Authorization": f"Bearer {tenant['access_token']}"}
            policy = make_policy(headers, rule_type="keyword", rule_text="badword")
    """
    def _make(
        jwt_headers: dict,
        rule_type: str = "keyword",
        rule_text: str = "test-block",
        name: str | None = None,
    ) -> dict:
        resp = client.post(
            "/api/v1/policies/",
            headers=jwt_headers,
            json={
                "name": name or f"policy-{uuid4()}",
                "rule_type": rule_type,
                "rule_text": rule_text,
                "is_enabled": True,
            },
        )
        assert resp.status_code == 201, f"Policy creation failed with status {resp.status_code}: {resp.text}"
        return resp.json()

    return _make


@pytest.fixture
def seed_audit_logs():
    """Return a callable that inserts audit logs directly into the DB.

    Usage::

        def test_foo(make_tenant, seed_audit_logs):
            tenant = make_tenant()
            tenant_id = UUID(tenant["tenant_id"])
            seed_audit_logs(tenant_id, n=5, action="BLOCKED", days_ago=1)
    """
    def _seed(
        tenant_id: UUID,
        n: int = 10,
        action: str = "ALLOWED",
        days_ago: float = 0.0,
    ) -> None:
        sync_url = settings.database_url.replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )
        engine = create_engine(sync_url)
        insert_sql = text(
            """
            INSERT INTO audit_logs (
                id, tenant_id, session_id, hook_type, action,
                violation_type, severity, input_preview, details,
                payload_hash, processing_ms, ip_address, created_at
            ) VALUES (
                :id, :tenant_id, :session_id, :hook_type, :action,
                :violation_type, :severity, :input_preview,
                CAST(:details AS jsonb), :payload_hash, :processing_ms,
                CAST(:ip_address AS inet), :created_at
            )
            """
        )
        base_time = datetime.now(timezone.utc) - timedelta(days=days_ago)
        with engine.begin() as conn:
            for i in range(n):
                conn.execute(insert_sql, {
                    "id": str(uuid4()),
                    "tenant_id": str(tenant_id),
                    "session_id": f"seed-{i}",
                    "hook_type": "access",
                    "action": action,
                    "violation_type": "prompt_injection" if action == "BLOCKED" else None,
                    "severity": "high" if action == "BLOCKED" else "low",
                    "input_preview": f"seeded message {i}",
                    "details": '{"seeded": true}',
                    "payload_hash": f"hash-{i}",
                    "processing_ms": 10 + i * 5,
                    "ip_address": None,
                    "created_at": base_time - timedelta(minutes=i),
                })

    return _seed
