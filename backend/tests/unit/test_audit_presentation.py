from copy import deepcopy
from datetime import datetime, timezone
from ipaddress import ip_address
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.audit import _anchoring_view, _audit_log_view, _csv_safe_cell
from app.api.v1 import audit as audit_api
from app.config import settings


def _legacy_audit_row(**overrides):
    values = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": "legacy-session-alice",
        "hook_type": "post_execution",
        "action": "BLOCKED",
        "violation_type": "prompt_injection",
        "severity": "high",
        "input_preview": (
            "Email alice@example.com; "
            "Bearer abcdefghijklmnopqrstuvwxyz123456"
        ),
        "details": {
            "request": {
                "message": "Contact alice@example.com",
                "api_key": "gsk_ABCDEFGHIJKLMNOPQRST1234",
                "password": "tiny",
            },
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
        },
        "payload_hash": "stored-legacy-hash-value",
        "policy_version": 1,
        "algorand_tx_id": "mock_tx_deadbeef",
        "processing_ms": 10,
        "ip_address": ip_address("203.0.113.10"),
        "user_agent": "Client Bearer abcdefghijklmnopqrstuvwxyz123456",
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_legacy_audit_view_sanitizes_copy_and_preserves_stored_hash_and_row():
    row = _legacy_audit_row()
    original_details = deepcopy(row.details)
    original_preview = row.input_preview
    original_session_id = row.session_id
    original_ip_address = row.ip_address

    view = _audit_log_view(row)

    serialized = view.model_dump_json()
    assert "alice@example.com" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz123456" not in serialized
    assert "gsk_ABCDEFGHIJKLMNOPQRST1234" not in serialized
    assert "tiny" not in serialized
    assert original_session_id not in serialized
    assert str(original_ip_address) not in serialized
    assert view.payload_hash == "stored-legacy-hash-value"
    assert view.payload_hash_provenance == "stored_unverified"
    assert view.algorand_tx_id is None
    assert view.anchoring_status == "not_anchored"
    assert set(view.redacted_fields) == {
        "details",
        "input_preview",
        "ip_address",
        "session_id",
        "user_agent",
    }

    # Presentation sanitization must never write back into historical rows or
    # recompute the payload hash from a newly redacted display value.
    assert row.details == original_details
    assert row.input_preview == original_preview
    assert row.session_id == original_session_id
    assert row.ip_address == original_ip_address


def test_missing_hash_is_labeled_unavailable():
    view = _audit_log_view(_legacy_audit_row(payload_hash=None))

    assert view.payload_hash is None
    assert view.payload_hash_provenance == "unavailable"


def test_short_labeled_credentials_are_removed_from_preview_and_details():
    row = _legacy_audit_row(
        input_preview="password: pw and api key = ap",
        details={
            "api key": "k",
            "message": "api_key: ap",
        },
    )

    view = _audit_log_view(row)
    serialized = view.model_dump_json()

    assert "password: pw" not in serialized
    assert "api key = ap" not in serialized
    assert '"api key": "k"' not in serialized
    assert "api_key: ap" not in serialized
    assert view.details["api key"] == "[REDACTED]"


def test_oversized_sensitive_key_suffix_does_not_leak_its_value():
    oversized_key = f"{'x' * 80}_password"
    view = _audit_log_view(
        _legacy_audit_row(details={oversized_key: "tiny-secret-value"})
    )

    serialized = view.model_dump_json()
    assert "tiny-secret-value" not in serialized
    assert oversized_key not in serialized
    assert view.details == {"_omitted_items": 1}
    assert "details" in view.redacted_fields


def test_nested_details_use_one_shared_item_budget(monkeypatch):
    sanitizer_calls = 0
    original_sanitizer = audit_api.sanitize_audit_metadata

    def count_sanitizer_calls(value, *, max_length=256):
        nonlocal sanitizer_calls
        sanitizer_calls += 1
        return original_sanitizer(value, max_length=max_length)

    monkeypatch.setattr(audit_api, "sanitize_audit_metadata", count_sanitizer_calls)
    branches = {
        f"branch-{branch}": {
            f"child-{child}": {
                f"leaf-{leaf}": f"value-{branch}-{child}-{leaf}"
                for leaf in range(8)
            }
            for child in range(8)
        }
        for branch in range(8)
    }

    view = _audit_log_view(_legacy_audit_row(details=branches))

    assert sanitizer_calls < 250
    assert "details" in view.redacted_fields
    assert len(view.details) < len(branches)
    assert len(view.model_dump_json()) < 12_000


def test_depth_boundary_omissions_use_the_shared_budgets():
    details = {"nested": [[[['x'] * 100_000]]]}

    view = _audit_log_view(_legacy_audit_row(details=details))
    serialized = view.model_dump_json()

    assert serialized.count("[OMITTED]") <= 100
    assert len(serialized) < 10_000
    assert "details" in view.redacted_fields


def test_redacted_dictionary_entries_still_consume_the_shared_item_budget():
    details = {f"password-{index}": "tiny" for index in range(200)}

    view = _audit_log_view(_legacy_audit_row(details=details))

    assert len(view.details) < len(details)
    assert "details" in view.redacted_fields
    assert all(
        value == "[REDACTED]"
        for value in view.details.values()
    )


def test_nested_details_obey_shared_character_budget():
    details = {f"field-{index}": "x" * 480 for index in range(24)}

    view = _audit_log_view(_legacy_audit_row(details=details))
    serialized = view.model_dump_json()

    assert len(serialized) < 10_000
    assert len(view.details) < len(details)
    assert "details" in view.redacted_fields


def test_anchoring_status_distinguishes_disabled_pending_and_real_ids(monkeypatch):
    monkeypatch.setattr(settings, "algorand_app_id", 0)
    assert _anchoring_view(None) == (None, "disabled")
    assert _anchoring_view("MOCK_TX_1234") == (None, "not_anchored")
    assert _anchoring_view("REAL_TX_ID") == ("REAL_TX_ID", "anchored")

    monkeypatch.setattr(settings, "algorand_app_id", 73)
    assert _anchoring_view(None) == (None, "pending")


def test_csv_cells_neutralize_formula_prefixes_without_changing_safe_values():
    assert _csv_safe_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _csv_safe_cell("   @SUM(A1:A2)") == "'   @SUM(A1:A2)"
    assert _csv_safe_cell("\t=1+1") == "'\t=1+1"
    assert _csv_safe_cell("ordinary audit value") == "ordinary audit value"
