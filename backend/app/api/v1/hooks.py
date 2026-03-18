"""SDK-facing endpoints: /check and /sanitize."""

import hashlib
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_tenant_by_api_key
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.hooks import (
    CheckRequest,
    CheckResponse,
    SanitizeRequest,
    SanitizeResponse,
)
from app.services.guardrails import injection_detector, pii_redactor, policy_engine
from app.worker import submit_to_chain_task

router = APIRouter(prefix="/hooks", tags=["SDK Hooks"])


async def _get_safety_config(db: AsyncSession, tenant_id: UUID) -> SafetyConfig:
    """Load tenant safety config or return default in-memory config."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = SafetyConfig(tenant_id=tenant_id)
    return config


@router.post("/check", response_model=CheckResponse)
async def check_message(
    body: CheckRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Run all configured safety checks and return a guardrail decision."""
    start = time.monotonic()
    violations: list[dict[str, str | float]] = []
    action = "ALLOWED"
    violation_type: str | None = None
    severity = "low"
    sanitized_message: str | None = None

    config = await _get_safety_config(db, tenant.id)

    if config.injection_protection:
        inj_result = injection_detector.detect(
            body.message, config.injection_sensitivity
        )
        if inj_result.is_injection:
            violations.append(
                {
                    "type": "prompt_injection",
                    "confidence": inj_result.confidence,
                    "method": inj_result.method,
                    "detail": inj_result.matched_pattern or "Model-detected injection",
                }
            )
            action = "BLOCKED"
            violation_type = "prompt_injection"
            severity = "critical"

    if action != "BLOCKED" and config.pii_redaction:
        pii_result = pii_redactor.redact(body.message, config.pii_types)
        if pii_result.pii_found:
            for redaction in pii_result.redactions:
                violations.append(
                    {
                        "type": f"pii_{redaction.type}",
                        "detail": f"Detected {redaction.type}: {redaction.original}",
                    }
                )
            action = "REDACTED"
            violation_type = "pii_detected"
            severity = "high"
            sanitized_message = pii_result.sanitized_text

    if action != "BLOCKED" and config.policy_enforcement:
        text_to_check = sanitized_message or body.message
        policy_result = await policy_engine.check_message(db, tenant.id, text_to_check)
        if policy_result.violated:
            for policy_match in policy_result.matched_policies:
                violations.append(
                    {
                        "type": "policy_violation",
                        "policy_name": policy_match.policy_name,
                        "similarity": policy_match.similarity_score,
                        "detail": f"Matches policy: {policy_match.rule_text[:100]}",
                    }
                )
            action = "BLOCKED"
            violation_type = "policy_violation"
            severity = "high"

    processing_ms = int((time.monotonic() - start) * 1000)
    payload_hash = hashlib.sha256(body.message.encode("utf-8")).hexdigest()

    audit_log = AuditLog(
        tenant_id=tenant.id,
        session_id=body.session_id,
        hook_type="pre_execution" if action == "BLOCKED" else "post_execution",
        action=action,
        violation_type=violation_type,
        severity=severity,
        input_preview=(sanitized_message or body.message)[:200],
        details={"violations": violations},
        payload_hash=payload_hash,
        policy_version=tenant.active_policy_version,
        processing_ms=processing_ms,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)

    if violation_type:
        submit_to_chain_task.delay(
            str(audit_log.id), action, violation_type, payload_hash
        )

    return CheckResponse(
        action=action,
        original_message=body.message if action == "REDACTED" else None,
        sanitized_message=sanitized_message,
        violations=violations,
        processing_ms=processing_ms,
        audit_id=audit_log.id,
    )


@router.post("/sanitize", response_model=SanitizeResponse)
async def sanitize_message(
    body: SanitizeRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> SanitizeResponse:
    """Apply PII redaction and log the sanitization audit event."""
    start = time.monotonic()

    config = await _get_safety_config(db, tenant.id)
    pii_result = pii_redactor.redact(
        body.message,
        config.pii_types if config.pii_redaction else [],
    )
    processing_ms = int((time.monotonic() - start) * 1000)

    audit_log = AuditLog(
        tenant_id=tenant.id,
        session_id=body.session_id,
        hook_type="post_execution",
        action="REDACTED" if pii_result.pii_found else "ALLOWED",
        violation_type="pii_detected" if pii_result.pii_found else None,
        severity="medium" if pii_result.pii_found else "low",
        input_preview=pii_result.sanitized_text[:200],
        details={
            "redactions": [
                {"type": r.type, "original": r.original} for r in pii_result.redactions
            ]
        },
        payload_hash=hashlib.sha256(body.message.encode("utf-8")).hexdigest(),
        processing_ms=processing_ms,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)

    return SanitizeResponse(
        sanitized_message=pii_result.sanitized_text,
        redactions=[
            {
                "type": r.type,
                "original": r.original,
                "replacement": r.replacement,
            }
            for r in pii_result.redactions
        ],
        processing_ms=processing_ms,
        audit_id=audit_log.id,
    )
