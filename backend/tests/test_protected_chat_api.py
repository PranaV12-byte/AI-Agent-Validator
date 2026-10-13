"""Route-level tests for the authenticated, local-only protected-chat demo.

Every generation client below is a fake.  The configured test DB and Redis
instance are used through the existing guarded test environment only.
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import demo as demo_api
from app.config import settings
from app.services.guardrails import protected_chat as protected_chat_flow
from app.services.guardrails.groq_client import GroqProviderError
from app.services.guardrails.pipeline import GuardrailEvaluation


class _FakeProvider:
    def __init__(self, answer: str = "A safe demo response.", error: Exception | None = None):
        self.answer = answer
        self.error = error
        self.calls: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture
def redis_probe():
    """Use only exact, tenant-scoped keys in the guarded test Redis DB."""
    connection = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield connection
    finally:
        connection.close()


def _auth(tenant: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tenant['access_token']}"}


@pytest.fixture
def make_demo_tenant(client: TestClient, make_tenant):
    """Extend the shared signup fixture with the authenticated tenant ID."""
    def _make(suffix: str | None = None) -> dict:
        tenant = make_tenant(suffix)
        profile = client.get("/api/v1/auth/me", headers=_auth(tenant))
        assert profile.status_code == 200
        return {**tenant, "tenant_id": profile.json()["id"]}

    return _make


def _lock_key(tenant: dict) -> str:
    return f"safebot:protected-chat:inflight:{tenant['tenant_id']}"


def _audit_rows(tenant_id: str) -> list[dict]:
    # tests/conftest.py rejects any database URL that is not the isolated test DB.
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id::text AS id, session_id, action, input_preview,
                           payload_hash, policy_version, details
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id
                      AND details->>'protected_chat' = 'true'
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings()
            return [dict(row) for row in rows]
    finally:
        engine.dispose()


def _fail_commit_at(monkeypatch, call_index: int) -> dict[str, int]:
    original_commit = AsyncSession.commit
    state = {"calls": 0}

    async def fail_selected_commit(session: AsyncSession) -> None:
        state["calls"] += 1
        if state["calls"] == call_index:
            raise RuntimeError("synthetic commit failure sentinel")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_selected_commit)
    return state


def test_protected_chat_routes_require_authentication(client: TestClient) -> None:
    readiness = client.get("/api/v1/demo/protected-chat/readiness")
    chat = client.post(
        "/api/v1/demo/protected-chat",
        json={"message": "synthetic request"},
    )

    assert readiness.status_code == 401
    assert chat.status_code == 401


def test_readiness_does_not_disclose_provider_credentials(
    client: TestClient, make_demo_tenant, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    sentinel = "synthetic-groq-secret-sentinel"
    monkeypatch.setattr(settings, "groq_api_key", sentinel)
    monkeypatch.setattr(settings, "groq_live_enabled", True)
    monkeypatch.setattr(settings, "groq_free_plan_confirmed", False)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)

    response = client.get(
        "/api/v1/demo/protected-chat/readiness", headers=_auth(tenant)
    )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["error_code"] == "groq_free_plan_unconfirmed"
    assert sentinel not in response.text
    assert provider.calls == []


def test_busy_tenant_lock_returns_409_without_provider_or_audit(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    assert redis_probe.set(key, "owned-by-this-test", nx=True, ex=90)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)
    try:
        response = client.post(
            "/api/v1/demo/protected-chat",
            headers=_auth(tenant),
            json={"message": "synthetic busy request"},
        )
    finally:
        redis_probe.delete(key)

    assert response.status_code == 409
    assert response.json()["status"] == "busy"
    assert response.json()["error_code"] == "protected_chat_busy"
    assert response.json()["audit_ids"] == []
    assert provider.calls == []
    assert _audit_rows(tenant["tenant_id"]) == []


def test_success_redacts_input_and_persists_hash_and_snapshot_provenance(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider("A safe demo response.")
    monkeypatch.setattr(demo_api, "groq_client", provider)
    raw_email = "alice@example.com"
    safe_prompt = "Please contact [EMAIL_REDACTED]"

    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": f"Please contact {raw_email}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"allowed", "redacted"}
    assert response.json()["answer"] == "A safe demo response."
    assert provider.calls == [safe_prompt]
    assert redis_probe.exists(key) == 0

    rows = _audit_rows(tenant["tenant_id"])
    assert [row["details"]["stage"] for row in rows] == ["pre", "post"]
    assert len(response.json()["audit_ids"]) == 2
    assert [row["id"] for row in rows] == response.json()["audit_ids"]
    assert raw_email not in repr(rows)
    assert rows[0]["payload_hash"] == hashlib.sha256(safe_prompt.encode()).hexdigest()
    assert rows[1]["payload_hash"] == hashlib.sha256(
        "A safe demo response.".encode()
    ).hexdigest()
    assert rows[0]["details"]["policy_snapshot_hash"]
    assert (
        rows[0]["details"]["policy_snapshot_hash"]
        == rows[1]["details"]["policy_snapshot_hash"]
    )
    assert rows[0]["details"]["conversation_id"] == rows[1]["details"]["conversation_id"]
    assert rows[0]["details"]["conversation_id"] != response.json()["conversation_id"]
    assert rows[0]["session_id"] == rows[1]["session_id"]
    assert all(row["policy_version"] == response.json()["policy_version"] for row in rows)


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "secret"),
    [
        (GroqProviderError("groq_provider_unavailable"), "groq_provider_unavailable", None),
        (RuntimeError("synthetic-provider-secret"), "groq_client_error", "synthetic-provider-secret"),
    ],
)
def test_provider_errors_are_safe_and_release_lock(
    client: TestClient,
    make_demo_tenant,
    redis_probe,
    monkeypatch,
    provider_error: Exception,
    expected_code: str,
    secret: str | None,
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider(error=provider_error)
    monkeypatch.setattr(demo_api, "groq_client", provider)

    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "safe synthetic provider input"},
    )

    assert response.status_code == 503
    assert response.json()["status"] == "provider_unavailable"
    assert response.json()["error_code"] == expected_code
    assert response.json()["answer"] is None
    assert provider.calls == ["safe synthetic provider input"]
    assert redis_probe.exists(key) == 0
    if secret:
        assert secret not in response.text
    rows = _audit_rows(tenant["tenant_id"])
    assert [row["details"]["stage"] for row in rows] == ["pre", "generation"]
    assert all(row["action"] == "ERROR" for row in rows if row["details"]["stage"] == "generation")


def test_pre_audit_commit_failure_prevents_generation_and_releases_lock(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)
    commits = _fail_commit_at(monkeypatch, 1)

    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "safe synthetic pre-audit input"},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "audit_unavailable"
    assert response.json()["answer"] is None
    assert response.json()["audit_ids"] == []
    assert commits["calls"] == 1
    assert provider.calls == []
    assert redis_probe.exists(key) == 0
    assert _audit_rows(tenant["tenant_id"]) == []


def test_post_audit_commit_failure_never_returns_generated_answer(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider("Synthetic answer must stay withheld.")
    monkeypatch.setattr(demo_api, "groq_client", provider)
    commits = _fail_commit_at(monkeypatch, 2)

    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "safe synthetic post-audit input"},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "audit_unavailable"
    assert response.json()["answer"] is None
    assert "Synthetic answer must stay withheld." not in response.text
    assert len(response.json()["audit_ids"]) == 1
    assert commits["calls"] == 2
    assert provider.calls == ["safe synthetic post-audit input"]
    assert redis_probe.exists(key) == 0
    rows = _audit_rows(tenant["tenant_id"])
    assert len(rows) == 1
    assert rows[0]["details"]["stage"] == "pre"


def test_uncertain_judge_failure_is_audited_and_never_forwarded(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)

    async def uncertain_judge(*_args, snapshot, **_kwargs) -> GuardrailEvaluation:
        return GuardrailEvaluation(
            status="evaluation_failed",
            safe_text=None,
            reason="The policy judgment could not be completed.",
            violations=(),
            error_code="policy_judge_unavailable",
            failure_codes=("policy_judge_unavailable",),
            policy_version=snapshot.policy_version,
            policy_snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode="closed",
            fallback_message=snapshot.config.fallback_message,
            redaction_counts={},
        )

    monkeypatch.setattr(protected_chat_flow, "evaluate_guardrails", uncertain_judge)
    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "synthetic input requiring an uncertain judgment"},
    )

    assert response.status_code == 503
    assert response.json()["status"] == "evaluation_failed"
    assert response.json()["error_code"] == "policy_judge_unavailable"
    assert response.json()["answer"] is None
    assert provider.calls == []
    assert len(response.json()["audit_ids"]) == 1
    assert redis_probe.exists(key) == 0
    rows = _audit_rows(tenant["tenant_id"])
    assert len(rows) == 1
    assert rows[0]["action"] == "ERROR"
    assert rows[0]["details"]["evaluation_status"] == "evaluation_failed"
    assert rows[0]["details"]["evaluation_failures"] == ["policy_judge_unavailable"]


def test_total_work_deadline_cancels_slow_guardrail_path_and_releases_lock(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)
    monkeypatch.setattr(protected_chat_flow, "PROTECTED_CHAT_WORK_TIMEOUT_SECONDS", 0.05)

    async def quick_snapshot(_db, _tenant_id, policy_version, _config):
        return protected_chat_flow.GuardrailSnapshot(
            policy_version=policy_version,
            config=protected_chat_flow._default_config(),
            policies=(),
            policy_snapshot_hash="synthetic-snapshot-hash",
        )

    monkeypatch.setattr(protected_chat_flow, "load_guardrail_snapshot", quick_snapshot)

    async def never_finishes(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(protected_chat_flow, "evaluate_guardrails", never_finishes)
    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "synthetic deadline input"},
    )

    assert response.status_code == 503
    assert response.json()["status"] == "evaluation_failed"
    assert response.json()["error_code"] == "protected_chat_deadline_exceeded"
    assert response.json()["answer"] is None
    assert len(response.json()["audit_ids"]) == 1
    assert provider.calls == []
    assert redis_probe.exists(key) == 0
    rows = _audit_rows(tenant["tenant_id"])
    assert len(rows) == 1
    assert rows[0]["details"]["stage"] == "pre"
    assert rows[0]["action"] == "ERROR"


def test_audit_write_deadline_fails_closed_before_generation(
    client: TestClient, make_demo_tenant, redis_probe, monkeypatch
) -> None:
    tenant = make_demo_tenant()
    key = _lock_key(tenant)
    provider = _FakeProvider()
    monkeypatch.setattr(demo_api, "groq_client", provider)
    monkeypatch.setattr(
        protected_chat_flow, "PROTECTED_CHAT_AUDIT_WRITE_TIMEOUT_SECONDS", 0.01
    )

    async def never_commits(_session: AsyncSession) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(AsyncSession, "commit", never_commits)
    response = client.post(
        "/api/v1/demo/protected-chat",
        headers=_auth(tenant),
        json={"message": "synthetic audit deadline input"},
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "audit_unavailable"
    assert response.json()["answer"] is None
    assert response.json()["audit_ids"] == []
    assert provider.calls == []
    assert redis_probe.exists(key) == 0
    assert _audit_rows(tenant["tenant_id"]) == []
