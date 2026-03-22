"""SDK-facing endpoints: /check and /sanitize."""

import hashlib
import time
from uuid import UUID
from collections.abc import Callable

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.dependencies import get_tenant_by_api_key
from app.core.rate_limit import limiter
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.hooks import (
    CheckRequest,
    CheckResponse,
    SanitizeRequest,
    SanitizeResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.services.guardrails import injection_detector, pii_redactor, policy_engine
from app.services.perf_trace import emit_timing, should_trace
from app.worker import submit_to_chain_task
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/hooks", tags=["SDK Hooks"])
validate_router = APIRouter(tags=["SDK Hooks"])
logger = structlog.get_logger()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def _timed_threadpool_call(
    call: Callable[[], object],
    *,
    trace_enabled: bool,
    event_name: str,
    tenant_id: UUID,
) -> object:
    started = time.perf_counter() if trace_enabled else 0.0
    result = await run_in_threadpool(call)
    if trace_enabled:
        emit_timing(
            event_name,
            tenant_id=str(tenant_id),
            elapsed_ms=_elapsed_ms(started),
        )
    return result


async def _get_safety_config(db: AsyncSession, tenant_id: UUID) -> SafetyConfig:
    """Load tenant safety config or return default in-memory config."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = SafetyConfig(tenant_id=tenant_id)
    return config


async def _insert_validate_audit_log(
    tenant_id: UUID,
    user_id: str | None,
    action: str,
    reason: str,
    prompt: str,
    latency_ms: int,
    risk_score: float,
    triggered_rules: list[str],
    request: Request,
) -> None:
    """Write validate endpoint telemetry into audit logs."""
    try:
        payload_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        violation_type = triggered_rules[0] if triggered_rules else None
        severity = (
            "critical" if action == "block" else "medium" if action == "flag" else "low"
        )

        async with AsyncSessionLocal() as db:
            log = AuditLog(
                tenant_id=tenant_id,
                session_id=user_id,
                hook_type="access",
                action="BLOCKED" if action == "block" else "ALLOWED",
                violation_type=violation_type,
                severity=severity,
                input_preview=prompt[:200],
                details={
                    "endpoint_called": "/api/v1/validate",
                    "latency_ms": latency_ms,
                    "risk_score": risk_score,
                    "action_taken": action,
                    "triggered_rules": triggered_rules,
                    "reason": reason,
                },
                payload_hash=payload_hash,
                processing_ms=latency_ms,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        logger.exception(
            "validate_audit_insert_failed",
            tenant_id=str(tenant_id),
            action=action,
            error=str(exc),
        )


@validate_router.post("/validate", response_model=ValidateResponse)
@router.post("/validate", response_model=ValidateResponse)
@limiter.limit("100/minute")
async def validate_prompt(
    body: ValidateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> ValidateResponse:
    """Unified high-performance guardrail validation endpoint."""
    start = time.monotonic()
    trace_enabled = should_trace()
    config = await _get_safety_config(db, tenant.id)

    triggered_rules: list[str] = []
    redacted_text: str | None = None
    reason = "Allowed"
    max_risk_score = 0.0

    sensitivity_thresholds = {
        "strict": 0.6,
        "moderate": 0.7,
        "lenient": 0.8,
    }

    if config.injection_protection:
        injection_result = await _timed_threadpool_call(
            lambda: injection_detector.detect(
                body.prompt, config.injection_sensitivity
            ),
            trace_enabled=trace_enabled,
            event_name="perf.validate.injection_detect",
            tenant_id=tenant.id,
        )
        if injection_result.is_injection:
            triggered_rules.append("prompt_injection")
            max_risk_score = max(max_risk_score, float(injection_result.confidence))
            reason = "Prompt Injection Detected"

    if config.pii_redaction:
        pii_result = await _timed_threadpool_call(
            lambda: pii_redactor.redact(body.prompt, config.pii_types),
            trace_enabled=trace_enabled,
            event_name="perf.validate.pii_redact",
            tenant_id=tenant.id,
        )
        if pii_result.pii_found:
            triggered_rules.append("pii_detected")
            max_risk_score = max(max_risk_score, 0.9)
            redacted_text = pii_result.sanitized_text
            if reason == "Allowed":
                reason = "PII Detected"

    threshold = sensitivity_thresholds.get(config.injection_sensitivity, 0.7)
    if triggered_rules and max_risk_score >= threshold:
        action = "block" if config.fail_mode == "closed" else "flag"
    else:
        action = "allow"

    if action == "allow" and redacted_text:
        action = "flag" if config.fail_mode == "open" else "block"

    latency_ms = int((time.monotonic() - start) * 1000)
    if trace_enabled:
        emit_timing(
            "perf.validate.total",
            tenant_id=str(tenant.id),
            elapsed_ms=latency_ms,
            action=action,
            triggered_rules=triggered_rules,
        )
    background_tasks.add_task(
        _insert_validate_audit_log,
        tenant.id,
        body.user_id,
        action,
        reason,
        body.prompt,
        latency_ms,
        max_risk_score,
        triggered_rules,
        request,
    )

    return ValidateResponse(
        action=action,
        reason=reason,
        redacted_text=redacted_text,
    )


@router.post("/check", response_model=CheckResponse)
async def check_message(
    body: CheckRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Run all configured safety checks and return a guardrail decision."""
    start = time.monotonic()
    trace_enabled = should_trace()
    violations: list[dict[str, str | float]] = []
    action = "ALLOWED"
    violation_type: str | None = None
    severity = "low"
    sanitized_message: str | None = None

    config = await _get_safety_config(db, tenant.id)

    if config.global_block_enabled:
        processing_ms = int((time.monotonic() - start) * 1000)
        payload_hash = hashlib.sha256(body.message.encode("utf-8")).hexdigest()
        audit_log = AuditLog(
            tenant_id=tenant.id,
            session_id=body.session_id,
            hook_type="pre_execution",
            action="BLOCKED",
            violation_type="global_block",
            severity="critical",
            input_preview=body.message[:200],
            details={"reason": "global_block_enabled"},
            payload_hash=payload_hash,
            policy_version=tenant.active_policy_version,
            processing_ms=processing_ms,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(audit_log)

        submit_to_chain_task.delay(
            str(audit_log.id),
            "BLOCKED",
            "global_block",
            payload_hash,
        )

        return CheckResponse(
            action="BLOCKED",
            original_message=None,
            sanitized_message=config.fallback_message,
            violations=[{"type": "global_block", "detail": "Global block is enabled"}],
            processing_ms=processing_ms,
            audit_id=audit_log.id,
        )

    if config.injection_protection:
        inj_result = await _timed_threadpool_call(
            lambda: injection_detector.detect(
                body.message, config.injection_sensitivity
            ),
            trace_enabled=trace_enabled,
            event_name="perf.check.injection_detect",
            tenant_id=tenant.id,
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
        pii_result = await _timed_threadpool_call(
            lambda: pii_redactor.redact(body.message, config.pii_types),
            trace_enabled=trace_enabled,
            event_name="perf.check.pii_redact",
            tenant_id=tenant.id,
        )
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
    if trace_enabled:
        emit_timing(
            "perf.check.total",
            tenant_id=str(tenant.id),
            elapsed_ms=processing_ms,
            action=action,
        )
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
    trace_enabled = should_trace()

    config = await _get_safety_config(db, tenant.id)

    if config.global_block_enabled:
        processing_ms = int((time.monotonic() - start) * 1000)
        audit_log = AuditLog(
            tenant_id=tenant.id,
            session_id=body.session_id,
            hook_type="post_execution",
            action="BLOCKED",
            violation_type="global_block",
            severity="critical",
            input_preview=body.message[:200],
            details={"reason": "global_block_enabled"},
            payload_hash=hashlib.sha256(body.message.encode("utf-8")).hexdigest(),
            processing_ms=processing_ms,
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(audit_log)

        return SanitizeResponse(
            sanitized_message=config.fallback_message,
            redactions=[],
            processing_ms=processing_ms,
            audit_id=audit_log.id,
        )
    pii_result = await _timed_threadpool_call(
        lambda: pii_redactor.redact(
            body.message,
            config.pii_types if config.pii_redaction else [],
        ),
        trace_enabled=trace_enabled,
        event_name="perf.sanitize.pii_redact",
        tenant_id=tenant.id,
    )
    processing_ms = int((time.monotonic() - start) * 1000)
    if trace_enabled:
        emit_timing(
            "perf.sanitize.total",
            tenant_id=str(tenant.id),
            elapsed_ms=processing_ms,
        )

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
