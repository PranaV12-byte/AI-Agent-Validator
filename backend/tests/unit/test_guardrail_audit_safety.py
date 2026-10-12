"""Audit evidence must not retain source PII, independent of tenant settings."""

from app.services.guardrails import audit_safety


def test_audit_evidence_redacts_preview_and_hashes_only_safe_text() -> None:
    source = "Email alice@example.com; phone +91 98765 43210"

    evidence = audit_safety.make_safe_audit_evidence(source)

    assert evidence.input_preview is not None
    assert "alice@example.com" not in evidence.input_preview
    assert "98765 43210" not in evidence.input_preview
    assert evidence.payload_hash is not None
    assert evidence.redaction_counts["email"] == 1
    assert evidence.redaction_counts["phone"] == 1


def test_audit_evidence_omits_preview_and_hash_when_redaction_fails(monkeypatch) -> None:
    def _fail(*_args, **_kwargs):
        raise RuntimeError("synthetic redactor failure")

    monkeypatch.setattr(audit_safety.pii_redactor, "redact", _fail)

    evidence = audit_safety.make_safe_audit_evidence("alice@example.com")

    assert evidence.input_preview is None
    assert evidence.payload_hash is None
    assert evidence.redaction_counts == {}


def test_audit_evidence_redacts_bearer_api_keys_and_jwt_literals() -> None:
    bearer = "Bearer abcdefghijklmnopqrstuvwxyz123456"
    groq_key = "gsk_ABCDEFGHIJKLMNOPQRST1234"
    jwt_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzYWZlIn0.signaturevalue123456"

    evidence = audit_safety.make_safe_audit_evidence(
        f"{bearer} {groq_key} {jwt_token}"
    )

    assert evidence.input_preview is not None
    assert bearer not in evidence.input_preview
    assert groq_key not in evidence.input_preview
    assert jwt_token not in evidence.input_preview
    assert evidence.redaction_counts["secret"] >= 3


def test_audit_evidence_redacts_space_separated_credential_labels() -> None:
    evidence = audit_safety.make_safe_audit_evidence(
        "api key: abcdefghijklmnop; access token=zyxwvutsrqponmlk"
    )

    assert evidence.input_preview is not None
    assert "abcdefghijklmnop" not in evidence.input_preview
    assert "zyxwvutsrqponmlk" not in evidence.input_preview
    assert evidence.redaction_counts["secret"] == 2


def test_audit_evidence_redacts_safe_bot_hex_keys_and_json_key_values() -> None:
    hex_key = "a" * 64
    json_secret = '{"api_key":"synthetic-json-secret-value"}'

    evidence = audit_safety.make_safe_audit_evidence(
        f"{hex_key} {json_secret}"
    )

    assert evidence.input_preview is not None
    assert hex_key not in evidence.input_preview
    assert "synthetic-json-secret-value" not in evidence.input_preview
    assert evidence.redaction_counts["secret"] == 2


def test_audit_evidence_redacts_short_labeled_credentials() -> None:
    evidence = audit_safety.make_safe_audit_evidence(
        'password: tiny; api_key: abc; api key: abc; '
        '{"password":"tiny","api_key":"abc"}'
    )

    assert evidence.input_preview is not None
    for secret in ("tiny", "abc"):
        assert secret not in evidence.input_preview
    assert evidence.redaction_counts["secret"] == 5


def test_audit_identifiers_are_stable_pseudonyms_and_metadata_is_sanitized() -> None:
    identifier = "alice@example.com"
    first = audit_safety.pseudonymize_audit_identifier(
        identifier,
        namespace="session",
    )
    second = audit_safety.pseudonymize_audit_identifier(
        identifier,
        namespace="session",
    )
    metadata = audit_safety.sanitize_audit_metadata(
        f"Client {identifier}; Bearer abcdefghijklmnopqrstuvwxyz123456"
    )

    assert first == second
    assert first is not None and first.startswith("id_")
    assert identifier not in first
    assert metadata is not None
    assert identifier not in metadata
    assert "Bearer abcdefghijklmnopqrstuvwxyz123456" not in metadata
