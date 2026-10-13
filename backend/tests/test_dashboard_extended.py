"""
Extended dashboard integration tests — stats correctness, 7-day window,
safety config all-field persistence, and validation edge cases.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signup(client: TestClient, suffix: str = None) -> dict:
    suffix = suffix or str(uuid4())
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "DashExt Co",
            "email": f"dashext-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_tenant_id(client: TestClient, token: str) -> str:
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert resp.status_code == 200
    return resp.json()["id"]


def _seed_log(
    tenant_id: str,
    action: str,
    processing_ms: int | None,
    days_ago: float = 0.0,
) -> None:
    """Insert a single audit log with configurable age."""
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(sync_url)
    insert_sql = text(
        """
        INSERT INTO audit_logs (
            id, tenant_id, hook_type, action, severity, details, processing_ms, created_at
        ) VALUES (
            gen_random_uuid(), :tenant_id, 'access', :action, 'low',
            '{}'::jsonb, :processing_ms,
            NOW() - CAST(:days_ago_interval AS interval)
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(insert_sql, {
            "tenant_id": tenant_id,
            "action": action,
            "processing_ms": processing_ms,
            "days_ago_interval": f"{days_ago} days",
        })


def _seed_chat_log(
    tenant_id: str,
    conversation_id: str,
    stage: str,
    action: str,
    evaluation_status: str,
    processing_ms: int,
    *,
    violations: list[dict] | None = None,
    failures: list[str] | None = None,
) -> None:
    """Insert one protected-chat stage using pseudonymous synthetic correlation."""
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(sync_url)
    insert_sql = text(
        """
        INSERT INTO audit_logs (
            id, tenant_id, session_id, hook_type, action, severity, details,
            processing_ms, created_at
        ) VALUES (
            gen_random_uuid(), :tenant_id, :session_id, :hook_type, :action,
            'low', CAST(:details AS jsonb), :processing_ms, NOW()
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(
            insert_sql,
            {
                "tenant_id": tenant_id,
                "session_id": f"id_{conversation_id}",
                "hook_type": f"protected_chat_{stage}",
                "action": action,
                "details": json.dumps(
                    {
                        "protected_chat": True,
                        "conversation_id": f"id_{conversation_id}",
                        "stage": stage,
                        "evaluation_status": evaluation_status,
                        "evaluation_failures": failures or [],
                        "violations": violations or [],
                    }
                ),
                "processing_ms": processing_ms,
            },
        )


# ---------------------------------------------------------------------------
# 2E-1: Stats correctness
# ---------------------------------------------------------------------------

def test_stats_new_tenant_returns_zeros(client: TestClient) -> None:
    """Brand-new tenant with no traffic → all stats are zero."""
    auth = _signup(client)
    resp = client.get("/api/v1/dashboard/stats", headers=_auth_headers(auth["access_token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 0
    assert data["blocked_requests"] == 0


def test_stats_counts_only_own_tenant(client: TestClient) -> None:
    """Tenant B's traffic is not visible in Tenant A's stats."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)
    tid_a = _get_tenant_id(client, tenant_a["access_token"])
    tid_b = _get_tenant_id(client, tenant_b["access_token"])

    for _ in range(10):
        _seed_log(tid_a, "ALLOWED", 50, days_ago=0.01)
    for _ in range(5):
        _seed_log(tid_b, "ALLOWED", 50, days_ago=0.01)

    stats_a = client.get("/api/v1/dashboard/stats", headers=_auth_headers(tenant_a["access_token"]))
    stats_b = client.get("/api/v1/dashboard/stats", headers=_auth_headers(tenant_b["access_token"]))

    assert stats_a.json()["total_requests"] == 10
    assert stats_b.json()["total_requests"] == 5
    assert stats_a.json()["allowed_requests"] == 10
    assert stats_a.json()["error_requests"] == 0


def test_stats_7day_window_excludes_older_logs(client: TestClient) -> None:
    """Logs older than 7 days are excluded from the stats window."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    _seed_log(tid, "BLOCKED", 100, days_ago=8.0)   # outside window
    _seed_log(tid, "ALLOWED", 100, days_ago=0.5)   # inside window

    resp = client.get("/api/v1/dashboard/stats", headers=_auth_headers(auth["access_token"]))
    data = resp.json()
    assert data["total_requests"] == 1
    assert data["blocked_requests"] == 0


def test_stats_blocked_count_is_accurate(client: TestClient) -> None:
    """3 ALLOWED + 2 BLOCKED → blocked_requests=2, total_requests=5."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    for _ in range(3):
        _seed_log(tid, "ALLOWED", 50)
    for _ in range(2):
        _seed_log(tid, "BLOCKED", 100)

    resp = client.get("/api/v1/dashboard/stats", headers=_auth_headers(auth["access_token"]))
    data = resp.json()
    assert data["total_requests"] == 5
    assert data["blocked_requests"] == 2
    assert data["allowed_requests"] == 3


def test_stats_count_protected_chat_once_and_exclude_errors_from_allowed(client: TestClient) -> None:
    auth = _signup(client)
    tenant_id = _get_tenant_id(client, auth["access_token"])

    _seed_chat_log(tenant_id, "allowed", "pre", "ALLOWED", "allowed", 10)
    _seed_chat_log(tenant_id, "allowed", "post", "ALLOWED", "allowed", 15)
    _seed_chat_log(
        tenant_id,
        "blocked",
        "pre",
        "BLOCKED",
        "blocked",
        20,
        violations=[{"type": "policy_violation"}],
    )
    _seed_chat_log(
        tenant_id,
        "error",
        "pre",
        "ERROR",
        "evaluation_failed",
        25,
        failures=["llm_judge_uncertain"],
    )
    _seed_chat_log(tenant_id, "redacted", "pre", "REDACTED", "redacted", 30)
    _seed_chat_log(tenant_id, "redacted", "post", "ALLOWED", "allowed", 20)
    _seed_chat_log(tenant_id, "incomplete", "pre", "ALLOWED", "allowed", 15)

    response = client.get(
        "/api/v1/dashboard/stats",
        headers=_auth_headers(auth["access_token"]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in (
        "total_requests",
        "blocked_requests",
        "allowed_requests",
        "redacted_requests",
        "error_requests",
        "avg_latency_ms",
    )} == {
        "total_requests": 5,
        "blocked_requests": 1,
        "allowed_requests": 1,
        "redacted_requests": 1,
        "error_requests": 2,
        "avg_latency_ms": 27.0,
    }
    daily = payload["daily_trend"]
    today = datetime.now(timezone.utc).date()
    assert len(daily) == 7
    assert daily[0]["date"] == (today - timedelta(days=6)).isoformat()
    assert daily[-1]["date"] == today.isoformat()
    for field in (
        "allowed_requests",
        "redacted_requests",
        "blocked_requests",
        "error_requests",
    ):
        assert sum(day[field] for day in daily) == payload[field]


def test_stats_avg_latency_calculation(client: TestClient) -> None:
    """3 logs with 10ms, 20ms, 30ms → avg_latency_ms == 20.0."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    for ms in (10, 20, 30):
        _seed_log(tid, "ALLOWED", ms)

    resp = client.get("/api/v1/dashboard/stats", headers=_auth_headers(auth["access_token"]))
    avg = resp.json()["avg_latency_ms"]
    assert abs(avg - 20.0) < 1.0  # allow floating-point fuzz


def test_stats_average_latency_ignores_missing_conversation_latency(client: TestClient) -> None:
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    _seed_log(tid, "ALLOWED", 100)
    _seed_log(tid, "ALLOWED", None)

    resp = client.get(
        "/api/v1/dashboard/stats",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["total_requests"] == 2
    assert resp.json()["avg_latency_ms"] == 100.0


# ---------------------------------------------------------------------------
# 2E-2: Safety config persistence
# ---------------------------------------------------------------------------

def test_safety_config_all_fields_update_and_persist(client: TestClient) -> None:
    """PUT with all known fields → GET returns all fields updated."""
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])

    payload = {
        "global_block_enabled": True,
        "injection_protection": False,
        "injection_sensitivity": "lenient",
        "pii_redaction": True,
        "pii_types": ["email", "phone"],
        "policy_enforcement": False,
        "fail_mode": "open",
        "fallback_message": "All blocked",
        "log_retention_days": 30,
    }

    put_resp = client.put("/api/v1/dashboard/safety-config", headers=headers, json=payload)
    assert put_resp.status_code == 200

    get_resp = client.get("/api/v1/dashboard/safety-config", headers=headers)
    assert get_resp.status_code == 200
    cfg = get_resp.json()

    assert cfg["global_block_enabled"] is True
    assert cfg["injection_protection"] is False
    assert cfg["injection_sensitivity"] == "lenient"
    assert cfg["pii_redaction"] is True
    assert cfg["policy_enforcement"] is False
    assert cfg["fail_mode"] == "open"
    assert cfg["fallback_message"] == "All blocked"
    assert cfg["log_retention_days"] == 30


def test_safety_config_partial_update_leaves_other_fields_unchanged(client: TestClient) -> None:
    """Partial PUT only touches the given fields; others retain defaults."""
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])

    # Get initial state
    initial = client.get("/api/v1/dashboard/safety-config", headers=headers).json()
    original_retention = initial["log_retention_days"]

    # Update only global_block_enabled
    client.put("/api/v1/dashboard/safety-config", headers=headers, json={"global_block_enabled": True})

    after = client.get("/api/v1/dashboard/safety-config", headers=headers).json()
    assert after["global_block_enabled"] is True
    assert after["log_retention_days"] == original_retention  # unchanged


@pytest.mark.parametrize(
    "path",
    ["/api/v1/dashboard/safety-config", "/api/v1/policies/config"],
)
@pytest.mark.parametrize(
    "payload",
    [
        {"injection_protection": None},
        {"fallback_message": "x" * 2001},
        {"unexpected": True},
    ],
)
def test_both_config_routes_reject_null_oversized_and_unknown_fields(
    client: TestClient,
    path: str,
    payload: dict[str, object],
) -> None:
    auth = _signup(client)

    response = client.put(
        path,
        headers=_auth_headers(auth["access_token"]),
        json=payload,
    )

    assert response.status_code == 422


def test_safety_config_enforcement_change_bumps_active_policy_version(client: TestClient) -> None:
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])
    before = client.get("/api/v1/auth/me", headers=headers).json()["active_policy_version"]

    response = client.put(
        "/api/v1/dashboard/safety-config",
        headers=headers,
        json={"global_block_enabled": True},
    )

    assert response.status_code == 200
    after = client.get("/api/v1/auth/me", headers=headers).json()["active_policy_version"]
    assert after == before + 1


def test_safety_config_fail_mode_persists_correctly(client: TestClient) -> None:
    """fail_mode value persists through PUT/GET cycle (dashboard endpoint stores as varchar)."""
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])

    # Note: dashboard safety-config stores as varchar; enum validation is on /policies/config
    resp = client.put("/api/v1/dashboard/safety-config", headers=headers, json={"fail_mode": "open"})
    assert resp.status_code == 200
    assert resp.json()["fail_mode"] == "open"

    resp = client.put("/api/v1/dashboard/safety-config", headers=headers, json={"fail_mode": "closed"})
    assert resp.status_code == 200
    assert resp.json()["fail_mode"] == "closed"


def test_safety_config_log_retention_min_1(client: TestClient) -> None:
    """log_retention_days=0 → 422; log_retention_days=1 → 200."""
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])

    resp_zero = client.put("/api/v1/dashboard/safety-config", headers=headers, json={"log_retention_days": 0})
    assert resp_zero.status_code == 422

    resp_one = client.put("/api/v1/dashboard/safety-config", headers=headers, json={"log_retention_days": 1})
    assert resp_one.status_code == 200


def test_safety_config_injection_sensitivity_persists(client: TestClient) -> None:
    """injection_sensitivity values persist through PUT/GET (dashboard endpoint stores as varchar)."""
    auth = _signup(client)
    headers = _auth_headers(auth["access_token"])

    # Note: enum validation (strict/moderate/lenient) is on /policies/config, not /dashboard/safety-config
    for val in ("strict", "moderate", "lenient"):
        resp = client.put(
            "/api/v1/dashboard/safety-config",
            headers=headers,
            json={"injection_sensitivity": val},
        )
        assert resp.status_code == 200, f"Expected 200 for sensitivity={val}"
        assert resp.json()["injection_sensitivity"] == val


def test_safety_config_negative_retention_days_returns_422(client: TestClient) -> None:
    """log_retention_days=-1 → 422."""
    auth = _signup(client)
    resp = client.put(
        "/api/v1/dashboard/safety-config",
        headers=_auth_headers(auth["access_token"]),
        json={"log_retention_days": -1},
    )
    assert resp.status_code == 422


def test_safety_config_requires_auth(client: TestClient) -> None:
    """GET /dashboard/safety-config without token → 401."""
    resp = client.get("/api/v1/dashboard/safety-config")
    assert resp.status_code == 401
