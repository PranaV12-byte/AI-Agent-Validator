"""
Unit tests for PIIRedactor — no DB, no Redis, no HTTP required.

Tests cover all Indian PII regex patterns (Aadhaar, PAN, email, phone, UPI),
edge-case inputs, pii_types filtering, and model readiness state.
"""
import pytest

from app.services.guardrails.pii_redactor import PIIRedactor, RedactionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redactor() -> PIIRedactor:
    """Return a fresh PIIRedactor (regex-only, no spaCy required)."""
    return PIIRedactor()


# ---------------------------------------------------------------------------
# 1B-1: Email redaction
# ---------------------------------------------------------------------------

def test_email_redaction_standard() -> None:
    """Standard email address is replaced with [EMAIL_REDACTED]."""
    r = _redactor()
    result = r.redact("Contact alice@example.com for details")
    assert "[EMAIL_REDACTED]" in result.sanitized_text
    assert "alice@example.com" not in result.sanitized_text
    assert result.pii_found is True


def test_email_redaction_plus_addressing() -> None:
    """Email with + addressing is redacted."""
    r = _redactor()
    result = r.redact("Send to user+tag@example.com please")
    assert "[EMAIL_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_email_redaction_multiple_in_text() -> None:
    """Multiple emails in the same text are all redacted."""
    r = _redactor()
    result = r.redact("From: a@x.com to b@y.org and c@z.co.in")
    assert result.sanitized_text.count("[EMAIL_REDACTED]") == 3


def test_email_not_redacted_when_type_excluded() -> None:
    """Email is NOT redacted when pii_types does not include 'email'."""
    r = _redactor()
    result = r.redact("Email alice@example.com here", pii_types=["phone"])
    assert "alice@example.com" in result.sanitized_text
    assert result.pii_found is False


def test_email_mask_stored_in_redactions() -> None:
    """Redactions list contains partial mask (first2***@***)."""
    r = _redactor()
    result = r.redact("alice@example.com")
    assert len(result.redactions) >= 1
    item = result.redactions[0]
    assert item.type == "email"
    assert item.original.startswith("al")  # first 2 chars of "alice"
    assert "***@***" in item.original
    assert item.replacement == "[EMAIL_REDACTED]"


# ---------------------------------------------------------------------------
# 1B-2: Phone redaction (Indian numbers)
# ---------------------------------------------------------------------------

def test_phone_redaction_10digit() -> None:
    """10-digit Indian mobile (starting 6-9) is redacted."""
    r = _redactor()
    result = r.redact("Call me at 9876543210 today")
    assert "[PHONE_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_phone_redaction_formatted_with_country_code() -> None:
    """Number with +91 prefix is redacted."""
    r = _redactor()
    result = r.redact("My number is +91 98765 43210")
    assert "[PHONE_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_phone_redaction_with_dash_separator() -> None:
    """Number formatted with dashes is redacted."""
    r = _redactor()
    result = r.redact("Reach out at +91-98765-43210")
    assert "[PHONE_REDACTED]" in result.sanitized_text


def test_phone_mask_shows_last4() -> None:
    """Phone mask in redactions preserves last 4 digits."""
    r = _redactor()
    result = r.redact("9876543210")
    assert result.pii_found is True
    item = result.redactions[0]
    assert item.original.endswith("3210")  # last 4 of 9876543210


def test_phone_starting_with_5_not_matched() -> None:
    """Number starting with 5 does NOT match Indian phone regex."""
    r = _redactor()
    result = r.redact("Call 5123456789")
    assert "[PHONE_REDACTED]" not in result.sanitized_text
    assert result.pii_found is False


# ---------------------------------------------------------------------------
# 1B-3: Aadhaar redaction
# ---------------------------------------------------------------------------

def test_aadhaar_redaction_with_spaces() -> None:
    """12-digit Aadhaar with spaces → [AADHAAR_REDACTED] in sanitized_text."""
    r = _redactor()
    result = r.redact("My Aadhaar is 1234 5678 9012")
    assert "[AADHAAR_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_aadhaar_redaction_with_dashes() -> None:
    """12-digit Aadhaar with dashes → [AADHAAR_REDACTED]."""
    r = _redactor()
    result = r.redact("Aadhaar: 1234-5678-9012")
    assert "[AADHAAR_REDACTED]" in result.sanitized_text


def test_aadhaar_redaction_no_separator() -> None:
    """12-digit Aadhaar with no separator → [AADHAAR_REDACTED]."""
    r = _redactor()
    result = r.redact("Aadhaar: 123456789012")
    assert "[AADHAAR_REDACTED]" in result.sanitized_text


def test_aadhaar_last4_preserved_in_mask() -> None:
    """The mask stored in redactions[].original shows XXXX-XXXX-{last4}."""
    r = _redactor()
    result = r.redact("1234 5678 9999")
    assert result.pii_found is True
    item = result.redactions[0]
    assert item.original == "XXXX-XXXX-9999"
    assert item.replacement == "[AADHAAR_REDACTED]"


def test_aadhaar_11_digits_not_matched() -> None:
    """11-digit number is not matched as Aadhaar."""
    r = _redactor()
    result = r.redact("1234 5678 901")
    assert "[AADHAAR_REDACTED]" not in result.sanitized_text


# ---------------------------------------------------------------------------
# 1B-4: PAN redaction
# ---------------------------------------------------------------------------

def test_pan_redaction() -> None:
    """Valid PAN card number → [PAN_REDACTED] in sanitized_text."""
    r = _redactor()
    result = r.redact("PAN: ABCDE1234F")
    assert "[PAN_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_pan_mask_shows_last5() -> None:
    """PAN mask in redactions is XXXXX + last 5 chars."""
    r = _redactor()
    result = r.redact("ABCDE1234F")
    assert result.pii_found is True
    item = result.redactions[0]
    assert item.original == "XXXXX1234F"  # last 5 of ABCDE1234F


def test_pan_lowercase_not_matched() -> None:
    """Lowercase PAN is not redacted (regex requires uppercase A-Z)."""
    r = _redactor()
    result = r.redact("abcde1234f")
    assert "[PAN_REDACTED]" not in result.sanitized_text
    assert result.pii_found is False


def test_pan_partial_match_not_flagged() -> None:
    """Partial PAN (4 chars only) is not matched."""
    r = _redactor()
    result = r.redact("ABCD1234")
    assert "[PAN_REDACTED]" not in result.sanitized_text


# ---------------------------------------------------------------------------
# 1B-5: UPI ID redaction
# ---------------------------------------------------------------------------

def test_upi_redaction_non_gmail() -> None:
    """UPI ID with non-email domain → [UPI_REDACTED]."""
    r = _redactor()
    result = r.redact("Pay to user@okaxis")
    assert "[UPI_REDACTED]" in result.sanitized_text
    assert result.pii_found is True


def test_upi_redaction_phonepe() -> None:
    """PhonePe-style text UPI ID (non-phone prefix) → [UPI_REDACTED]."""
    r = _redactor()
    result = r.redact("Pay to rajesh.kumar@ybl for services", pii_types=["upi"])
    assert "[UPI_REDACTED]" in result.sanitized_text


def test_upi_not_redacted_for_gmail() -> None:
    """user@gmail.com is treated as email, not UPI (excluded domain)."""
    r = _redactor()
    result = r.redact("user@gmail.com", pii_types=["upi"])
    # gmail.com is in the exclusion list for UPI
    assert "[UPI_REDACTED]" not in result.sanitized_text


def test_upi_not_redacted_for_yahoo() -> None:
    """user@yahoo.com is treated as email, not UPI."""
    r = _redactor()
    result = r.redact("user@yahoo.com", pii_types=["upi"])
    assert "[UPI_REDACTED]" not in result.sanitized_text


def test_upi_not_redacted_for_outlook() -> None:
    """user@outlook.com excluded from UPI detection."""
    r = _redactor()
    result = r.redact("user@outlook.com", pii_types=["upi"])
    assert "[UPI_REDACTED]" not in result.sanitized_text


def test_upi_mask_shows_domain() -> None:
    """UPI mask: ***@{domain}."""
    r = _redactor()
    result = r.redact("myid@okicici", pii_types=["upi"])
    assert result.pii_found is True
    item = result.redactions[0]
    assert item.original == "***@okicici"


# ---------------------------------------------------------------------------
# 1B-6: Multiple PII types in same text
# ---------------------------------------------------------------------------

def test_multiple_pii_in_one_text() -> None:
    """Text with email + phone → both redacted."""
    r = _redactor()
    text = "Email: user@test.com, Phone: 9876543210"
    result = r.redact(text)
    assert "[EMAIL_REDACTED]" in result.sanitized_text
    assert "[PHONE_REDACTED]" in result.sanitized_text
    assert result.pii_found is True
    assert len(result.redactions) >= 2


def test_aadhaar_and_pan_in_same_text() -> None:
    """Text with both Aadhaar and PAN → both redacted."""
    r = _redactor()
    text = "Aadhaar: 1234 5678 9012, PAN: ABCDE1234F"
    result = r.redact(text)
    assert "[AADHAAR_REDACTED]" in result.sanitized_text
    assert "[PAN_REDACTED]" in result.sanitized_text


# ---------------------------------------------------------------------------
# 1B-7: Edge cases
# ---------------------------------------------------------------------------

def test_no_pii_in_text() -> None:
    """Clean text → unchanged sanitized_text, pii_found=False."""
    r = _redactor()
    text = "Hello world, this is a normal sentence."
    result = r.redact(text)
    assert result.sanitized_text == text
    assert result.pii_found is False
    assert result.redactions == []


def test_empty_string_no_crash() -> None:
    """Empty string → no crash, returns empty sanitized_text."""
    r = _redactor()
    result = r.redact("")
    assert result.sanitized_text == ""
    assert result.pii_found is False


def test_empty_pii_types_list() -> None:
    """pii_types=[] → no redaction even when PII present."""
    r = _redactor()
    result = r.redact("alice@example.com and 9876543210", pii_types=[])
    assert "alice@example.com" in result.sanitized_text
    assert "9876543210" in result.sanitized_text
    assert result.pii_found is False


def test_returns_redaction_result_dataclass() -> None:
    """redact() always returns a RedactionResult instance."""
    r = _redactor()
    result = r.redact("Hello")
    assert isinstance(result, RedactionResult)
    assert hasattr(result, "sanitized_text")
    assert hasattr(result, "redactions")
    assert hasattr(result, "pii_found")


def test_original_text_not_mutated() -> None:
    """Original text string is not mutated; sanitized_text is a new string."""
    r = _redactor()
    text = "Contact alice@example.com"
    original = text
    result = r.redact(text)
    assert text == original  # original unchanged
    assert result.sanitized_text != text


# ---------------------------------------------------------------------------
# 1B-8: Model readiness
# ---------------------------------------------------------------------------

def test_is_ready_false_before_load() -> None:
    """`is_ready` is False on fresh PIIRedactor."""
    r = PIIRedactor()
    assert r.is_ready is False


def test_is_ready_true_after_load_model() -> None:
    """`is_ready` is True after load_model() called (even without spaCy)."""
    r = PIIRedactor()
    r.load_model()  # Falls back gracefully if spaCy not available
    assert r.is_ready is True


def test_redact_works_without_spacy() -> None:
    """Regex-only mode (no spaCy) still redacts PII correctly."""
    r = PIIRedactor()
    # Do NOT call load_model — pure regex mode
    result = r.redact("alice@example.com")
    assert "[EMAIL_REDACTED]" in result.sanitized_text
