from types import SimpleNamespace

import pytest

from app import worker
from app.config import settings
from app.services import algorand_writer


def test_disabled_chain_writer_skips_without_creating_client(monkeypatch):
    monkeypatch.setattr(settings, "algorand_app_id", 0)
    monkeypatch.setattr(
        algorand_writer,
        "_get_client",
        lambda: pytest.fail("disabled chain mode must not create an SDK client"),
    )

    assert algorand_writer.submit_audit_to_algorand(
        "audit-id", "BLOCKED", "policy_violation", "a" * 64
    ) is None
    assert algorand_writer.register_policy_on_algorand("policy-id", "b" * 64) is None


def test_chain_tasks_do_not_persist_mock_transaction_ids(monkeypatch):
    monkeypatch.setattr(settings, "algorand_app_id", 0)
    audit_updates: list[tuple[str, str]] = []
    policy_updates: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "_update_audit_tx_id", lambda *args: audit_updates.append(args))
    monkeypatch.setattr(worker, "_update_policy_tx_id", lambda *args: policy_updates.append(args))

    audit_result = worker.submit_to_chain_task.run(
        "audit-id", "BLOCKED", "policy_violation", "a" * 64
    )
    policy_result = worker.register_policy_on_chain_task.run("policy-id", "b" * 64)

    assert audit_result == {"status": "skipped", "reason": "chain_not_configured"}
    assert policy_result == {"status": "skipped", "reason": "chain_not_configured"}
    assert audit_updates == []
    assert policy_updates == []


def test_retry_error_and_type_metadata_do_not_include_provider_message(monkeypatch):
    secret_detail = "synthetic-provider-token-do-not-log-123456"
    captured: dict[str, object] = {}

    def fail_with_provider_detail(*_args):
        raise RuntimeError(secret_detail)

    def capture_safe_retry(*_args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("synthetic-retry-sentinel")

    monkeypatch.setattr(algorand_writer, "submit_audit_to_algorand", fail_with_provider_detail)
    monkeypatch.setattr(worker.submit_to_chain_task, "retry", capture_safe_retry)

    with pytest.raises(RuntimeError, match="synthetic-retry-sentinel") as retry_error:
        worker.submit_to_chain_task.run("audit-id", "BLOCKED", "policy_violation", "a" * 64)

    safe_exception = captured["exc"]
    assert str(safe_exception) == "chain_submission_failed"
    assert secret_detail not in str(safe_exception)
    assert retry_error.value.__context__ is None
    assert worker._safe_error_type(RuntimeError(secret_detail)) == "RuntimeError"


def test_retention_is_tenant_scoped_batched_and_never_less_than_one_day(monkeypatch):
    tenants = [
        SimpleNamespace(tenant_id="tenant-a", log_retention_days=0),
        SimpleNamespace(tenant_id="tenant-b", log_retention_days=-5),
    ]

    class FakeResult:
        def __init__(self, *, rows=None, rowcount=1):
            self.rows = rows or []
            self.rowcount = rowcount

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def __init__(self):
            self.deletes: list[dict[str, object]] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            if "SELECT tenant_id, log_retention_days" in str(statement):
                return FakeResult(rows=tenants)
            self.deletes.append(dict(params or {}))
            return FakeResult(rowcount=1)

        def commit(self):
            pass

    connection = FakeConnection()

    class FakeEngine:
        def connect(self):
            return connection

    monkeypatch.setattr(worker, "_get_sync_engine", lambda: FakeEngine())

    result = worker.purge_old_audit_logs_task.run()

    assert result == {"deleted": 2}
    assert connection.deletes == [
        {"tid": "tenant-a", "days": 1},
        {"tid": "tenant-b", "days": 1},
    ]
