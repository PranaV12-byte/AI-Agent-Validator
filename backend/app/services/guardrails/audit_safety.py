"""PII-safe audit evidence shared by every text-processing endpoint."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from dataclasses import dataclass

from app.config import settings
from app.services.guardrails.pii_redactor import PII_PATTERNS, pii_redactor

_SECRET_PATTERNS = (
    re.compile(
        r"\b(?:bearer|basic)\s+[A-Za-z0-9._~+/-]+=*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:api[\s_-]?key|access[\s_-]?token|refresh[\s_-]?token|"
        r"auth[\s_-]?token|client[\s_-]?secret|private[\s_-]?key|"
        r"secret|password|token)\b[\"']?\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9._~+/-]{1,256}={0,2}[\"']?",
        re.IGNORECASE,
    ),
    # SafeBot API keys are secrets.token_hex(32): unlabelled 64-character hex.
    re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:gsk_[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{16,}|"
        r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[0-9A-Z]{16})\b"
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)


@dataclass(frozen=True)
class SafeAuditEvidence:
    input_preview: str | None
    payload_hash: str | None
    redaction_counts: dict[str, int]


def _sanitize_text(value: str) -> tuple[str, dict[str, int]]:
    result = pii_redactor.redact(value, list(PII_PATTERNS))
    safe_text = result.sanitized_text
    counts = dict(Counter(item.type for item in result.redactions))
    for pattern in _SECRET_PATTERNS:
        safe_text, count = pattern.subn("[SECRET_REDACTED]", safe_text)
        if count:
            counts["secret"] = counts.get("secret", 0) + count
    return safe_text, counts


def sanitize_text_for_external_judge(value: str) -> tuple[str, dict[str, int]]:
    """Redact recognized PII and credential-like values before external judging.

    Unlike audit previews, this returns the full sanitized bounded input for a
    caller that needs to evaluate its meaning. A sanitization exception must be
    treated as an evaluator failure; callers must not fall back to raw text.
    """
    return _sanitize_text(value)


def pseudonymize_audit_identifier(value: str | None, *, namespace: str) -> str | None:
    """Create a stable per-secret pseudonym without persisting user identifiers."""
    if value is None or not value.strip():
        return None
    material = f"audit:{namespace}:{value.strip()}".encode("utf-8")
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        material,
        hashlib.sha256,
    ).hexdigest()
    return f"id_{digest[:32]}"


def sanitize_audit_metadata(value: str | None, *, max_length: int = 256) -> str | None:
    """Sanitize bounded metadata such as User-Agent before persisting it."""
    if value is None:
        return None
    try:
        safe_text, _ = _sanitize_text(value)
    except Exception:
        return None
    return safe_text[:max_length]


def make_safe_audit_evidence(message: str) -> SafeAuditEvidence:
    """Create bounded evidence after scanning every supported PII type.

    If sanitization fails, omit both preview and hash rather than persisting
    potentially sensitive source text. Redaction values are never returned.
    """
    try:
        safe_text, counts = _sanitize_text(message)
    except Exception:
        return SafeAuditEvidence(None, None, {})

    return SafeAuditEvidence(
        input_preview=safe_text[:200],
        payload_hash=hashlib.sha256(safe_text.encode("utf-8")).hexdigest(),
        redaction_counts=counts,
    )
