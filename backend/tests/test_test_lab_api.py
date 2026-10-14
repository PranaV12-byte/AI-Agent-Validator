"""Database-backed coverage for synthetic tests and decision reviews."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.safety_config import SafetyConfig
from app.schemas.test_lab import TestRunOutcome as RunOutcomeSchema
from app.services.guardrails.pipeline import (
    GuardrailConfigSnapshot,
    GuardrailEvaluation,
    GuardrailSnapshot,
)
from app.services.guardrails.policy_snapshot import PolicyRuleSnapshot
from app.api.v1 import test_lab as test_lab_api


_DEFAULT_CASE = {
    "name": "Synthetic greeting",
    "prompt": "Please say hello to fictional user Riley.",
    "expected_action": "allow",
    "synthetic_data_acknowledged": True,
}


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _tenant_id(client, auth: dict) -> str:
    response = client.get("/api/v1/auth/me", headers=_headers(auth))
    assert response.status_code == 200
    return response.json()["id"]


def _create_case(client, auth: dict, values: dict | None = None) -> dict:
    response = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json=values or _DEFAULT_CASE,
    )
    assert response.status_code == 201, f"Case creation failed with status {response.status_code}"
    return response.json()


def _snapshot(
    snapshot_hash: str = "a" * 64,
    *,
    policy_enforcement: bool = False,
    policies: tuple[PolicyRuleSnapshot, ...] = (),
) -> GuardrailSnapshot:
    config = GuardrailConfigSnapshot(
        global_block_enabled=False,
        injection_protection=False,
        injection_sensitivity="moderate",
        pii_redaction=False,
        pii_types=(),
        policy_enforcement=policy_enforcement,
        fail_mode="closed",
        fallback_message="Unavailable",
    )
    return GuardrailSnapshot(
        policy_version=1,
        config=config,
        policies=policies,
        policy_snapshot_hash=snapshot_hash,
    )


def _evaluation(
    snapshot: GuardrailSnapshot,
    *,
    status: str = "allowed",
    safe_text: str | None = "Synthetic response",
    failure_codes: tuple[str, ...] = (),
    redaction_counts: dict[str, int] | None = None,
) -> GuardrailEvaluation:
    return GuardrailEvaluation(
        status=status,  # type: ignore[arg-type]
        safe_text=safe_text,
        reason="Test-only deterministic result",
        violations=(),
        error_code=failure_codes[0] if failure_codes else None,
        failure_codes=failure_codes,
        policy_version=snapshot.policy_version,
        policy_snapshot_hash=snapshot.policy_snapshot_hash,
        fail_mode=snapshot.config.fail_mode,
        fallback_message=snapshot.config.fallback_message,
        redaction_counts=redaction_counts or {},
    )


def _current_snapshot(snapshot: GuardrailSnapshot):
    async def _capture(_db, tenant):
        return SafetyConfig(tenant_id=tenant.id), snapshot

    return _capture


def _sync_database_url() -> str:
    return settings.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)


def _usage_count(tenant_id: str) -> int:
    engine = create_engine(_sync_database_url())
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT COUNT(*) FROM api_usage WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar_one()
    finally:
        engine.dispose()


def test_test_lab_requires_jwt_and_keeps_cases_tenant_scoped(
    client, make_tenant
) -> None:
    assert client.get("/api/v1/test-lab/cases").status_code == 401
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    case_a = _create_case(client, tenant_a)
    case_b = _create_case(client, tenant_b)

    list_a = client.get("/api/v1/test-lab/cases", headers=_headers(tenant_a))
    list_b = client.get("/api/v1/test-lab/cases", headers=_headers(tenant_b))
    assert [case["id"] for case in list_a.json()["cases"]] == [case_a["id"]]
    assert [case["id"] for case in list_b.json()["cases"]] == [case_b["id"]]

    update = client.put(
        f"/api/v1/test-lab/cases/{case_a['id']}",
        headers=_headers(tenant_b),
        json={**_DEFAULT_CASE, "revision": 1},
    )
    delete = client.delete(
        f"/api/v1/test-lab/cases/{case_a['id']}", headers=_headers(tenant_b)
    )
    run = client.post(
        "/api/v1/test-lab/run",
        headers=_headers(tenant_b),
        json={"case_ids": [case_a["id"]]},
    )
    assert (update.status_code, delete.status_code, run.status_code) == (404, 404, 404)


def test_case_create_rejects_secrets_without_echoing_submitted_prompt(client, make_tenant) -> None:
    auth = make_tenant()
    secret = "demo-secret-should-not-appear-in-the-response"
    response = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json={
            **_DEFAULT_CASE,
            "prompt": f"Please use password={secret} in this example.",
        },
    )
    assert response.status_code == 422
    assert secret not in response.text

    no_ack = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json={**_DEFAULT_CASE, "synthetic_data_acknowledged": False},
    )
    assert no_ack.status_code == 422

    malformed_secret = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json={
            "prompt": f"Missing a name; never echo {secret}",
            "expected_action": "allow",
            "synthetic_data_acknowledged": True,
        },
    )
    assert malformed_secret.status_code == 422
    assert secret not in malformed_secret.text


def test_invalid_revision_and_missing_review_decision_never_echo_body_secrets(
    client, make_tenant
) -> None:
    auth = make_tenant()
    case = _create_case(client, auth)
    secret = "private-synthetic-credential-marker"
    invalid_revision = client.put(
        f"/api/v1/test-lab/cases/{case['id']}",
        headers=_headers(auth),
        json={**_DEFAULT_CASE, "prompt": f"Credential stays private {secret}", "revision": 0},
    )
    assert invalid_revision.status_code == 422
    assert secret not in invalid_revision.text

    tenant_id = _tenant_id(client, auth)
    audit_id = str(uuid4())
    engine = create_engine(_sync_database_url())
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, tenant_id, hook_type, action, severity, input_preview, details, "
                    "payload_hash, created_at) VALUES "
                    "(:audit_id, :tenant_id, 'test', 'ALLOWED', 'low', 'safe preview', "
                    "'{}'::jsonb, 'validation-test-hash', now())"
                ),
                {"audit_id": audit_id, "tenant_id": tenant_id},
            )
    finally:
        engine.dispose()
    missing_decision = client.put(
        f"/api/v1/audit/{audit_id}/feedback",
        headers=_headers(auth),
        json={"note": secret, "status": "open"},
    )
    assert missing_decision.status_code == 422
    assert secret not in missing_decision.text


def test_case_revision_conflicts_and_old_result_becomes_stale(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    case = _create_case(client, auth)
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))

    async def evaluate(_db, _tenant_id, _version, _config, _message, *, snapshot):
        return _evaluation(snapshot)

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", evaluate)
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)
    run = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert run.status_code == 200
    assert run.json()["results"][0]["status"] == "passed"

    update = client.put(
        f"/api/v1/test-lab/cases/{case['id']}",
        headers=_headers(auth),
        json={**_DEFAULT_CASE, "prompt": "A manually revised synthetic prompt.", "revision": 1},
    )
    assert update.status_code == 200
    assert update.json()["revision"] == 2
    assert update.json()["last_result"]["status"] == "stale"

    stale_update = client.put(
        f"/api/v1/test-lab/cases/{case['id']}",
        headers=_headers(auth),
        json={**_DEFAULT_CASE, "revision": 1},
    )
    assert stale_update.status_code == 409
    stored = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"][0]
    assert stored["prompt"] == "A manually revised synthetic prompt."


def test_run_result_is_discarded_when_case_revision_changes_mid_evaluation(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    case = _create_case(client, auth)
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)

    async def evaluate(_db, _tenant_id, _version, _config, _message, *, snapshot):
        engine = create_engine(_sync_database_url())
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE test_cases SET revision = revision + 1 WHERE id = :case_id"),
                    {"case_id": case["id"]},
                )
        finally:
            engine.dispose()
        return _evaluation(snapshot)

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", evaluate)
    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert response.status_code == 200
    outcome = response.json()["results"][0]
    assert outcome["status"] == "revision_conflict"
    assert outcome["case_revision"] == 1
    stored = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"][0]
    assert stored["revision"] == 2
    assert stored["last_result"] is None


def test_run_deadline_returns_and_saves_truthful_unavailable_result(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    first_case = _create_case(client, auth)
    second_case = _create_case(client, auth, {**_DEFAULT_CASE, "name": "Not started case"})
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)
    monkeypatch.setattr(test_lab_api, "RUN_DEADLINE_SECONDS", 0.01)

    async def slow_evaluation(_db, _tenant_id, _version, _config, _message, *, snapshot):
        await asyncio.sleep(0.05)
        return _evaluation(snapshot)

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", slow_evaluation)
    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert response.status_code == 200
    outcomes = {outcome["case_id"]: outcome for outcome in response.json()["results"]}
    assert outcomes[first_case["id"]]["status"] == "unavailable"
    assert outcomes[first_case["id"]]["failure_codes"] == ["run_deadline_exceeded"]
    assert outcomes[second_case["id"]]["status"] == "not_run"
    assert response.json()["unavailable"] == 1
    assert response.json()["not_run"] == 1
    stored = {
        case["id"]: case
        for case in client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"]
    }
    assert stored[first_case["id"]]["last_result"]["status"] == "unavailable"
    assert stored[second_case["id"]]["last_result"]["status"] == "not_run"


def test_run_savepoint_write_failure_is_reported_unavailable() -> None:
    class FailingSession:
        @asynccontextmanager
        async def begin_nested(self):
            yield

        async def execute(self, _statement):
            raise RuntimeError("simulated write failure")

    outcome = RunOutcomeSchema(
        case_id=uuid4(),
        case_revision=1,
        status="passed",
        expected_action="allow",
        observed_action="allow",
        completed_at=datetime.now(timezone.utc),
    )
    result = asyncio.run(
        test_lab_api._persist_outcome(
            outcome,
            tenant_id=uuid4(),
            db_session=FailingSession(),  # type: ignore[arg-type]
        )
    )
    assert result.status == "unavailable"
    assert result.observed_action is None
    assert result.failure_codes == ["result_persistence_failed"]


def test_case_create_commit_failure_is_not_reported_as_saved(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()

    async def fail_commit(_session):
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json=_DEFAULT_CASE,
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Could not save the test case"
    cases = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"]
    assert cases == []


def test_feedback_commit_failure_is_not_reported_as_saved(
    client, make_tenant, seed_audit_logs, monkeypatch
) -> None:
    auth = make_tenant()
    seed_audit_logs(UUID(_tenant_id(client, auth)), n=1)
    audit_id = client.get("/api/v1/audit/?limit=1", headers=_headers(auth)).json()["logs"][0]["id"]

    async def fail_commit(_session):
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = client.put(
        f"/api/v1/audit/{audit_id}/feedback",
        headers=_headers(auth),
        json={"decision": "correct", "status": "open"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Could not save the decision review"
    current = client.get(
        f"/api/v1/audit/{audit_id}/feedback", headers=_headers(auth)
    )
    assert current.status_code == 200
    assert current.json() is None


def test_run_commit_failure_cannot_return_passed_or_saved_result(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    _create_case(client, auth)
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)

    async def evaluate(_db, _tenant_id, _version, _config, _message, *, snapshot):
        return _evaluation(snapshot)

    async def fail_commit(_session):
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", evaluate)
    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert response.status_code == 200
    assert response.json()["passed"] == 0
    assert response.json()["unavailable"] == 1
    assert response.json()["results"][0]["failure_codes"] == ["result_commit_failed"]
    stored = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"][0]
    assert stored["last_result"] is None


async def _no_rate_limit(_tenant_id: UUID) -> None:
    return None


def test_case_cap_is_enforced_per_tenant(client, make_tenant) -> None:
    auth = make_tenant()
    for index in range(20):
        response = client.post(
            "/api/v1/test-lab/cases",
            headers=_headers(auth),
            json={**_DEFAULT_CASE, "name": f"Synthetic case {index + 1}"},
        )
        assert response.status_code == 201
    overflow = client.post(
        "/api/v1/test-lab/cases",
        headers=_headers(auth),
        json={**_DEFAULT_CASE, "name": "One too many"},
    )
    assert overflow.status_code == 409


def test_run_reuses_one_snapshot_and_creates_no_audit_or_usage_rows(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    tenant_id = _tenant_id(client, auth)
    case_a = _create_case(client, auth)
    case_b = _create_case(client, auth, {**_DEFAULT_CASE, "name": "Second case"})
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)
    seen_snapshots = []

    async def evaluate(_db, _tenant_id, _version, _config, _message, *, snapshot):
        seen_snapshots.append(snapshot)
        return _evaluation(snapshot, safe_text="Synthetic output for fictional user@example.com")

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", evaluate)
    audits_before = client.get("/api/v1/audit/?limit=200", headers=_headers(auth)).json()["total"]
    usage_before = _usage_count(tenant_id)

    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert response.status_code == 200
    data = response.json()
    assert data["passed"] == 2
    assert {item["case_id"] for item in data["results"]} == {case_a["id"], case_b["id"]}
    assert len(seen_snapshots) == 2 and seen_snapshots[0] is seen_snapshots[1]
    assert "user@example.com" not in response.text
    assert client.get("/api/v1/audit/?limit=200", headers=_headers(auth)).json()["total"] == audits_before
    assert _usage_count(tenant_id) == usage_before


def test_evaluation_failure_cannot_pass_an_expected_block_case(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    _create_case(
        client,
        auth,
        {**_DEFAULT_CASE, "expected_action": "block", "name": "Unavailable block check"},
    )
    snapshot = _snapshot()
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)

    async def failed_evaluation(_db, _tenant_id, _version, _config, _message, *, snapshot):
        return _evaluation(
            snapshot,
            status="evaluation_failed",
            safe_text=None,
            failure_codes=("pii_evaluation_failed",),
        )

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", failed_evaluation)
    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    outcome = response.json()["results"][0]
    assert response.status_code == 200
    assert outcome["status"] == "unavailable"
    assert outcome["observed_action"] is None
    assert response.json()["passed"] == 0


def test_external_judge_preflight_returns_unavailable_without_evaluation(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    _create_case(client, auth)
    policy = PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name="External judge rule",
        rule_type="llm_eval",
        rule_text="synthetic rubric",
        parameters_json='{"rubric":"synthetic rubric"}',
        is_enabled=True,
        policy_hash=None,
    )
    snapshot = _snapshot(policy_enforcement=True, policies=(policy,))
    monkeypatch.setattr(test_lab_api, "_current_snapshot", _current_snapshot(snapshot))
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)

    def unexpected_evaluation(*_args, **_kwargs):
        raise AssertionError("External-judge preflight must not call evaluation")

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", unexpected_evaluation)
    response = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    outcome = response.json()["results"][0]
    assert response.status_code == 200
    assert outcome["status"] == "unavailable"
    assert outcome["failure_codes"] == ["external_judge_required"]


def test_settings_fingerprint_change_marks_saved_result_stale(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    _create_case(client, auth)
    hashes = {"current": "a" * 64}

    async def capture(_db, tenant):
        return SafetyConfig(tenant_id=tenant.id), _snapshot(hashes["current"])

    monkeypatch.setattr(test_lab_api, "_current_snapshot", capture)
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)

    async def evaluate(_db, _tenant_id, _version, _config, _message, *, snapshot):
        return _evaluation(snapshot)

    monkeypatch.setattr(test_lab_api, "evaluate_guardrails", evaluate)
    run = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert run.json()["passed"] == 1
    hashes["current"] = "b" * 64
    cases = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"]
    assert cases[0]["last_result"]["status"] == "stale"


def test_real_shared_pipeline_and_persisted_settings_change_mark_result_stale(
    client, make_tenant, monkeypatch
) -> None:
    auth = make_tenant()
    _create_case(client, auth)
    monkeypatch.setattr(test_lab_api, "_enforce_run_rate_limit", _no_rate_limit)
    tenant_id = _tenant_id(client, auth)
    audits_before = client.get("/api/v1/audit/?limit=20", headers=_headers(auth)).json()["total"]
    usage_before = _usage_count(tenant_id)

    run = client.post("/api/v1/test-lab/run", headers=_headers(auth), json={})
    assert run.status_code == 200
    assert run.json()["results"][0]["status"] == "passed"
    old_hash = run.json()["results"][0]["snapshot_hash"]
    assert old_hash
    assert client.get("/api/v1/audit/?limit=20", headers=_headers(auth)).json()["total"] == audits_before
    assert _usage_count(tenant_id) == usage_before

    engine = create_engine(_sync_database_url())
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE safety_configs SET pii_redaction = NOT pii_redaction "
                    "WHERE tenant_id = :tenant_id"
                ),
                {"tenant_id": _tenant_id(client, auth)},
            )
    finally:
        engine.dispose()

    cases = client.get("/api/v1/test-lab/cases", headers=_headers(auth)).json()["cases"]
    assert cases[0]["last_result"]["status"] == "stale"


def test_review_upsert_is_tenant_scoped_and_csv_filter_matches_list(
    client, make_tenant, seed_audit_logs
) -> None:
    auth_a = make_tenant()
    auth_b = make_tenant()
    tenant_a = UUID(_tenant_id(client, auth_a))
    seed_audit_logs(tenant_a, n=2, action="BLOCKED")
    logs = client.get("/api/v1/audit/?limit=20", headers=_headers(auth_a)).json()["logs"]
    target = logs[0]
    original_hash = target["payload_hash"]

    created = client.put(
        f"/api/v1/audit/{target['id']}/feedback",
        headers=_headers(auth_a),
        json={"decision": "correct", "status": "open", "note": "Reviewed contact a@example.com"},
    )
    assert created.status_code == 200
    feedback_id = created.json()["id"]
    assert "a@example.com" not in created.json()["note"]

    updated = client.put(
        f"/api/v1/audit/{target['id']}/feedback",
        headers=_headers(auth_a),
        json={
            "decision": "incorrect",
            "expected_action": "allow",
            "status": "resolved",
            "note": "Reviewed by the team",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == feedback_id
    assert updated.json()["expected_action"] == "allow"

    wrong_tenant = client.get(
        f"/api/v1/audit/{target['id']}/feedback", headers=_headers(auth_b)
    )
    assert wrong_tenant.status_code == 404
    foreign_upsert = client.put(
        f"/api/v1/audit/{target['id']}/feedback",
        headers=_headers(auth_b),
        json={"decision": "unsure", "status": "open"},
    )
    foreign_conversion = client.post(
        f"/api/v1/test-lab/feedback/{feedback_id}/cases",
        headers=_headers(auth_b),
        json=_DEFAULT_CASE,
    )
    assert foreign_upsert.status_code == 404
    assert foreign_conversion.status_code == 404
    open_list = client.get("/api/v1/audit/?review_status=open", headers=_headers(auth_a))
    resolved_list = client.get("/api/v1/audit/?review_status=resolved", headers=_headers(auth_a))
    unreviewed_list = client.get("/api/v1/audit/?review_status=unreviewed", headers=_headers(auth_a))
    assert open_list.json()["total"] == 0
    assert resolved_list.json()["total"] == 1
    assert unreviewed_list.json()["total"] == 1
    export = client.get("/api/v1/audit/export?review_status=resolved", headers=_headers(auth_a))
    assert export.status_code == 200
    assert "review_status" in export.text.splitlines()[0]
    assert "resolved" in export.text.splitlines()[1]

    case = client.post(
        f"/api/v1/test-lab/feedback/{feedback_id}/cases",
        headers=_headers(auth_a),
        json={
            **_DEFAULT_CASE,
            "name": "Hand-authored follow-up",
            "prompt": "A synthetic scenario written from scratch by the reviewer.",
        },
    )
    assert case.status_code == 201
    assert case.json()["source_feedback_id"] == feedback_id
    assert case.json()["prompt"] == "A synthetic scenario written from scratch by the reviewer."
    assert "seeded message" not in case.json()["prompt"]

    malformed_feedback_id = str(uuid4())
    engine = create_engine(_sync_database_url())
    try:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO decision_feedback "
                        "(id, tenant_id, audit_log_id, decision, expected_action, status) "
                        "VALUES (:id, :tenant_id, :audit_id, 'incorrect', NULL, 'open')"
                    ),
                    {
                        "id": malformed_feedback_id,
                        "tenant_id": str(tenant_a),
                        "audit_id": logs[1]["id"],
                    },
                )
    finally:
        engine.dispose()

    engine = create_engine(_sync_database_url())
    try:
        with engine.connect() as connection:
            stored_hash = connection.execute(
                text("SELECT payload_hash FROM audit_logs WHERE id = :audit_id"),
                {"audit_id": target["id"]},
            ).scalar_one()
        assert stored_hash == original_hash

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM audit_logs WHERE id = :audit_id"),
                {"audit_id": target["id"]},
            )
            feedback_count = connection.execute(
                text("SELECT COUNT(*) FROM decision_feedback WHERE id = :feedback_id"),
                {"feedback_id": feedback_id},
            ).scalar_one()
            source_after_purge = connection.execute(
                text("SELECT source_feedback_id FROM test_cases WHERE id = :case_id"),
                {"case_id": case.json()["id"]},
            ).scalar_one()
        assert feedback_count == 0
        assert source_after_purge is None
    finally:
        engine.dispose()


def test_run_rate_limit_is_tenant_keyed(monkeypatch) -> None:
    seen_keys: list[str] = []

    class FakeRedis:
        count = 0

        async def eval(self, _script, _number_of_keys, key, _ttl):
            seen_keys.append(key)
            self.count += 1
            return self.count

    redis = FakeRedis()
    async def fake_get_redis():
        return redis

    monkeypatch.setattr(test_lab_api, "get_redis", fake_get_redis)
    tenant_id = uuid4()
    for _ in range(test_lab_api.RUN_RATE_LIMIT):
        asyncio.run(test_lab_api._enforce_run_rate_limit(tenant_id))
    with pytest.raises(HTTPException) as error:
        asyncio.run(test_lab_api._enforce_run_rate_limit(tenant_id))
    assert error.value.status_code == 429
    assert all(str(tenant_id) in key for key in seen_keys)
