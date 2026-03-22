from app.services.guardrails.pii_redactor import pii_redactor


def test_redacts_email_phone_and_aadhaar():
    text = (
        "Contact me at alice@example.com, phone +91 98765 43210, "
        "and Aadhaar 1234 5678 9012"
    )

    result = pii_redactor.redact(text)

    assert result.pii_found is True
    assert "[EMAIL_REDACTED]" in result.sanitized_text
    assert "[PHONE_REDACTED]" in result.sanitized_text
    assert "[AADHAAR_REDACTED]" in result.sanitized_text
    redaction_types = {item.type for item in result.redactions}
    assert {"email", "phone", "aadhaar"}.issubset(redaction_types)


def test_respects_selected_pii_types_only():
    text = "Email alice@example.com and PAN ABCDE1234F"

    result = pii_redactor.redact(text, pii_types=["pan"])

    assert result.pii_found is True
    assert "[PAN_REDACTED]" in result.sanitized_text
    assert "[EMAIL_REDACTED]" not in result.sanitized_text
    assert all(item.type == "pan" for item in result.redactions)


def test_upi_detection_skips_common_email_domains():
    result = pii_redactor.redact("Send money to alice@gmail.com", pii_types=["upi"])

    assert result.pii_found is False
    assert result.sanitized_text == "Send money to alice@gmail.com"


def test_detects_upi_for_non_email_handle():
    result = pii_redactor.redact("UPI is alice@oksbi", pii_types=["upi"])

    assert result.pii_found is True
    assert "[UPI_REDACTED]" in result.sanitized_text
    assert result.redactions[0].type == "upi"


def test_no_pii_returns_original_text_and_empty_redactions():
    text = "Hello team, please share the meeting notes."
    result = pii_redactor.redact(text)

    assert result.pii_found is False
    assert result.sanitized_text == text
    assert result.redactions == []
