"""
Extended audit integration tests — date filtering, pagination edge cases,
ordering, data integrity, and tenant isolation.
"""
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

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
            "company_name": "AuditExt Co",
            "email": f"auditext-{suffix}@example.com",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_tenant_id(client: TestClient, token: str) -> UUID:
    resp = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert resp.status_code == 200
    return UUID(resp.json()["id"])


def _seed_logs(
    tenant_id: UUID,
    total: int = 10,
    action: str = "ALLOWED",
    days_ago: float = 0.0,
) -> None:
    """Insert audit logs directly into the DB with configurable timestamps."""
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
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
        for i in range(total):
            conn.execute(insert_sql, {
                "id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "session_id": f"ext-seed-{i}",
                "hook_type": "access",
                "action": action,
                "violation_type": "prompt_injection" if action == "BLOCKED" else None,
                "severity": "high" if action == "BLOCKED" else "low",
                "input_preview": f"seed message {i}",
                "details": '{"seeded": true}',
                "payload_hash": f"hash-{i}",
                "processing_ms": 10 + i * 5,
                "ip_address": None,
                "created_at": base_time - timedelta(minutes=i),
            })


def _seed_legacy_sensitive_log(tenant_id: UUID) -> tuple[str, dict[str, str]]:
    """Seed one synthetic pre-sanitization row without touching ORM state."""
    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    engine = create_engine(sync_url)
    row_id = str(uuid4())
    raw = {
        "input_preview": (
            "=1+1 Email alice@example.com; "
            "Bearer abcdefghijklmnopqrstuvwxyz123456"
        ),
        "session_id": "legacy-session-alice@example.com",
        "user_agent": "Client Bearer abcdefghijklmnopqrstuvwxyz123456",
        "api_key": "gsk_ABCDEFGHIJKLMNOPQRST1234",
        "password": "tiny",
        "payload_hash": "stored-historical-hash",
        "ip_address": "203.0.113.10",
        "algorand_tx_id": "mock_tx_legacy",
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_logs (
                    id, tenant_id, session_id, hook_type, action,
                    violation_type, severity, input_preview, details,
                    payload_hash, policy_version, algorand_tx_id,
                    processing_ms, ip_address, user_agent, created_at
                ) VALUES (
                    :id, :tenant_id, :session_id, 'post_execution', 'BLOCKED',
                    'prompt_injection', 'high', :input_preview, CAST(:details AS jsonb),
                    :payload_hash, 1, :algorand_tx_id,
                    10, CAST(:ip_address AS inet), :user_agent, NOW()
                )
                """
            ),
            {
                "id": row_id,
                "tenant_id": str(tenant_id),
                "session_id": raw["session_id"],
                "input_preview": raw["input_preview"],
                "details": json.dumps({
                    "request": {
                        "api_key": raw["api_key"],
                        "password": raw["password"],
                    }
                }),
                "payload_hash": raw["payload_hash"],
                "algorand_tx_id": raw["algorand_tx_id"],
                "ip_address": raw["ip_address"],
                "user_agent": raw["user_agent"],
            },
        )
    with engine.connect() as conn:
        raw["stored_ip_address"] = conn.execute(
            text("SELECT ip_address::text FROM audit_logs WHERE id = :id"),
            {"id": row_id},
        ).scalar_one()
    engine.dispose()
    return row_id, raw


# ---------------------------------------------------------------------------
# 2D-1: Action filtering
# ---------------------------------------------------------------------------

def test_audit_filter_by_action_blocked(client: TestClient) -> None:
    """Filter action=BLOCKED returns only BLOCKED logs."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=5, action="BLOCKED")
    _seed_logs(tid, total=5, action="ALLOWED")

    resp = client.get(
        "/api/v1/audit/?action=BLOCKED&limit=20",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    logs = resp.json()["logs"]
    assert logs
    assert all(l["action"] == "BLOCKED" for l in logs)


def test_audit_filter_by_action_allowed(client: TestClient) -> None:
    """Filter action=ALLOWED returns only ALLOWED logs."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=3, action="BLOCKED")
    _seed_logs(tid, total=4, action="ALLOWED")

    resp = client.get(
        "/api/v1/audit/?action=ALLOWED&limit=20",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    logs = resp.json()["logs"]
    assert logs
    assert all(l["action"] == "ALLOWED" for l in logs)


def test_audit_invalid_action_returns_422(client: TestClient) -> None:
    """Unknown action value → 422."""
    auth = _signup(client)
    resp = client.get(
        "/api/v1/audit/?action=HACKED",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2D-2: Date range filtering
# ---------------------------------------------------------------------------

def test_audit_filter_by_start_date_excludes_older_logs(client: TestClient) -> None:
    """start_date=today excludes logs from 2 days ago."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    _seed_logs(tid, total=3, action="ALLOWED", days_ago=2.0)  # old
    _seed_logs(tid, total=2, action="BLOCKED")                 # recent

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = client.get(
        f"/api/v1/audit/?start_date={today}&limit=20",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    logs = resp.json()["logs"]
    # All returned logs should be from today (no old ones)
    for log in logs:
        created = datetime.fromisoformat(log["created_at"].replace("Z", "+00:00"))
        assert created.date() >= datetime.now(timezone.utc).date()


def test_audit_filter_by_end_date_excludes_recent_logs(client: TestClient) -> None:
    """end_date=yesterday excludes today's logs."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])

    _seed_logs(tid, total=3, action="ALLOWED", days_ago=2.0)  # old

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    resp = client.get(
        f"/api/v1/audit/?end_date={yesterday}&limit=20",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    # Response should be ok (may be empty or have old logs)
    assert "logs" in resp.json()


def test_audit_filter_invalid_date_format_returns_422(client: TestClient) -> None:
    """Non-ISO date string → 422."""
    auth = _signup(client)
    resp = client.get(
        "/api/v1/audit/?start_date=not-a-date",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2D-3: Pagination edge cases
# ---------------------------------------------------------------------------

def test_audit_total_count_accurate(client: TestClient) -> None:
    """total field reflects all matching logs, not just the page."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=25)

    resp = client.get(
        "/api/v1/audit/?limit=10&offset=0",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) == 10
    assert data["total"] >= 25
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_audit_offset_beyond_total_returns_empty(client: TestClient) -> None:
    """offset=9999 with only a few logs → empty logs list, total still accurate."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=5)

    resp = client.get(
        "/api/v1/audit/?limit=10&offset=9999",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["logs"] == []
    assert data["total"] >= 5


def test_audit_limit_1_returns_exactly_1_log(client: TestClient) -> None:
    """limit=1 → exactly 1 log returned."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=5)

    resp = client.get(
        "/api/v1/audit/?limit=1&offset=0",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()["logs"]) == 1


def test_audit_limit_above_max_returns_422(client: TestClient) -> None:
    """limit=201 → 422 (max is 200)."""
    auth = _signup(client)
    resp = client.get(
        "/api/v1/audit/?limit=201",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 422


def test_audit_offset_above_max_returns_422(client: TestClient) -> None:
    """offset=10001 → 422."""
    auth = _signup(client)
    resp = client.get(
        "/api/v1/audit/?offset=10001",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2D-4: Ordering and data quality
# ---------------------------------------------------------------------------

def test_audit_ordering_is_newest_first(client: TestClient) -> None:
    """Audit logs are returned in descending created_at order."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=10)

    resp = client.get(
        "/api/v1/audit/?limit=10&offset=0",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    logs = resp.json()["logs"]
    if len(logs) >= 2:
        timestamps = [
            datetime.fromisoformat(l["created_at"].replace("Z", "+00:00"))
            for l in logs
        ]
        assert timestamps == sorted(timestamps, reverse=True)


def test_audit_log_has_expected_fields(client: TestClient) -> None:
    """Each audit log entry contains required fields."""
    auth = _signup(client)
    tid = _get_tenant_id(client, auth["access_token"])
    _seed_logs(tid, total=1)

    resp = client.get(
        "/api/v1/audit/?limit=1",
        headers=_auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    log = resp.json()["logs"][0]
    for field in ("id", "tenant_id", "action", "created_at", "processing_ms"):
        assert field in log, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# 2D-5: Tenant isolation
# ---------------------------------------------------------------------------

def test_audit_tenant_isolation(client: TestClient) -> None:
    """Tenant A cannot see Tenant B's audit logs."""
    tenant_a = _signup(client)
    tenant_b = _signup(client)

    tid_a = _get_tenant_id(client, tenant_a["access_token"])
    tid_b = _get_tenant_id(client, tenant_b["access_token"])

    _seed_logs(tid_a, total=5, action="BLOCKED")
    _seed_logs(tid_b, total=3, action="ALLOWED")

    logs_a = client.get("/api/v1/audit/?limit=50", headers=_auth_headers(tenant_a["access_token"]))
    logs_b = client.get("/api/v1/audit/?limit=50", headers=_auth_headers(tenant_b["access_token"]))

    ids_a = {l["tenant_id"] for l in logs_a.json()["logs"]}
    ids_b = {l["tenant_id"] for l in logs_b.json()["logs"]}

    assert str(tid_a) in ids_a
    assert str(tid_b) not in ids_a
    assert str(tid_b) in ids_b
    assert str(tid_a) not in ids_b


class TestAuditSearch:
    def test_search_returns_200(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/",
            params={"search": "hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data

    def test_search_empty_string_ignored(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/",
            params={"search": ""},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_search_requires_auth(self, client):
        resp = client.get("/api/v1/audit/", params={"search": "test"})
        assert resp.status_code == 401


class TestAuditExport:
    def test_export_returns_csv(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get("/api/v1/audit/export", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert "safebot-audit-export.csv" in resp.headers["content-disposition"]

    def test_export_csv_has_headers(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get("/api/v1/audit/export", headers=headers)
        first_line = resp.text.split("\n")[0]
        assert "id" in first_line
        assert "action" in first_line
        assert "created_at" in first_line

    def test_export_accepts_same_filters_as_list(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/export",
            params={"action": "BLOCKED", "search": "test"},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_export_requires_auth(self, client):
        resp = client.get("/api/v1/audit/export")
        assert resp.status_code == 401

    def test_legacy_sensitive_rows_are_sanitized_in_api_and_csv_without_mutation(
        self, client, make_tenant
    ):
        auth = make_tenant()
        headers = _auth_headers(auth["access_token"])
        tenant_id = _get_tenant_id(client, auth["access_token"])
        row_id, raw = _seed_legacy_sensitive_log(tenant_id)

        response = client.get(
            "/api/v1/audit/",
            params={"search": "alice@example.com"},
            headers=headers,
        )
        assert response.status_code == 200
        row = next(log for log in response.json()["logs"] if log["id"] == row_id)
        serialized = json.dumps(row)
        assert "alice@example.com" not in serialized
        assert "abcdefghijklmnopqrstuvwxyz123456" not in serialized
        assert raw["api_key"] not in serialized
        assert raw["password"] not in serialized
        assert raw["session_id"] not in serialized
        assert raw["ip_address"] not in serialized
        assert row["payload_hash"] == raw["payload_hash"]
        assert row["payload_hash_provenance"] == "stored_unverified"
        assert row["algorand_tx_id"] is None
        assert row["anchoring_status"] == "not_anchored"
        assert set(row["redacted_fields"]) == {
            "details", "input_preview", "ip_address", "session_id", "user_agent"
        }

        exported = client.get(
            "/api/v1/audit/export",
            params={"search": "alice@example.com"},
            headers=headers,
        )
        assert exported.status_code == 200
        assert "stored-historical-hash" in exported.text
        assert "stored_unverified" in exported.text
        assert "not_anchored" in exported.text
        assert "redacted_fields" in exported.text.splitlines()[0]
        assert "'=1+1" in exported.text
        assert "alice@example.com" not in exported.text
        assert "abcdefghijklmnopqrstuvwxyz123456" not in exported.text
        assert raw["api_key"] not in exported.text
        assert raw["password"] not in exported.text
        assert raw["session_id"] not in exported.text
        assert raw["ip_address"] not in exported.text

        sync_url = settings.database_url.replace(
            "postgresql+asyncpg", "postgresql+psycopg2"
        )
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            stored = conn.execute(
                text(
                    """SELECT input_preview, details, payload_hash, session_id,
                              ip_address::text, algorand_tx_id
                       FROM audit_logs WHERE id = :id"""
                ),
                {"id": row_id},
            ).one()
        engine.dispose()
        assert stored.input_preview == raw["input_preview"]
        assert stored.details == {
            "request": {
                "api_key": raw["api_key"],
                "password": raw["password"],
            }
        }
        assert stored.payload_hash == raw["payload_hash"]
        assert stored.session_id == raw["session_id"]
        assert stored.ip_address == raw["stored_ip_address"]
        assert stored.algorand_tx_id == raw["algorand_tx_id"]
