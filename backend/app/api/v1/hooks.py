"""SDK-facing endpoints: /check and /sanitize."""

import asyncio
import time
from uuid import UUID

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
from app.services.guardrails.audit_safety import (
    make_safe_audit_evidence,
    pseudonymize_audit_identifier,
    sanitize_audit_metadata,
)
from app.services.guardrails.pipeline import GuardrailEvaluation, evaluate_guardrails
from app.services.perf_trace import emit_timing, should_trace
from app.worker import submit_to_chain_task

router = APIRouter(prefix="/hooks", tags=["SDK Hooks"])
validate_router = APIRouter(tags=["SDK Hooks"])
logger = structlog.get_logger()


async def _get_safety_config(db: AsyncSession, tenant_id: UUID) -> SafetyConfig:
    """Load tenant safety config or return default in-memory config."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        config = SafetyConfig(tenant_id=tenant_id)
    return config


def _audit_action(evaluation: GuardrailEvaluation) -> str:
    return {
        "allow": "ALLOWED",
        "redact": "REDACTED",
        "block": "BLOCKED",
    }[evaluation.action]


def _freeze_guardrail_request_context(
    tenant: Tenant,
) -> tuple[UUID, int]:
    """Copy identity/version before an evaluator may recover a failed SQL savepoint."""
    return UUID(str(tenant.id)), int(tenant.active_policy_version)


def _response_violations(evaluation: GuardrailEvaluation) -> list[dict[str, object]]:
    response: list[dict[str, object]] = []
    for finding in evaluation.violations:
        if finding["type"] == "pii_detected":
            for pii_type, count in evaluation.redaction_counts.items():
                response.append({"type": f"pii_{pii_type}", "count": count})
            continue
        response.append(dict(finding))
    return response


def _build_audit_log(
    *,
    tenant_id: UUID,
    session_id: str | None,
    hook_type: str,
    message: str,
    evaluation: GuardrailEvaluation,
    processing_ms: int,
    user_agent: str | None,
) -> AuditLog:
    evidence = make_safe_audit_evidence(message)
    violations = _response_violations(evaluation)
    violation_type = (
        str(evaluation.violations[0]["type"])
        if evaluation.violations
        else "evaluation_error"
        if evaluation.status == "evaluation_failed"
        else None
    )
    severity = (
        "critical"
        if evaluation.status == "blocked"
        else "high"
        if evaluation.status in ("redacted", "evaluation_failed")
        else "low"
    )
    return AuditLog(
        tenant_id=tenant_id,
        session_id=pseudonymize_audit_identifier(
            session_id,
            namespace=f"session:{tenant_id}",
        ),
        hook_type=hook_type,
        action=_audit_action(evaluation),
        violation_type=violation_type,
        severity=severity,
        input_preview=evidence.input_preview,
        details={
            "evaluation_status": evaluation.status,
            "error_code": evaluation.error_code,
            "evaluation_failures": list(evaluation.failure_codes),
            "reason": evaluation.reason,
            "violations": violations,
            "redaction_counts": evidence.redaction_counts,
            "policy_version": evaluation.policy_version,
            "policy_snapshot_hash": evaluation.policy_snapshot_hash,
        },
        payload_hash=evidence.payload_hash,
        policy_version=evaluation.policy_version,
        processing_ms=processing_ms,
        # Raw client IPs are identifying data; omit them from new audit records.
        ip_address=None,
        user_agent=sanitize_audit_metadata(user_agent),
    )


def _enqueue_chain_best_effort(audit_log: AuditLog, evaluation: GuardrailEvaluation) -> None:
    if evaluation.status not in ("blocked", "redacted") or not audit_log.payload_hash:
        return
    try:
        submit_to_chain_task.delay(
            str(audit_log.id),
            audit_log.action,
            audit_log.violation_type or "unknown",
            audit_log.payload_hash,
        )
    except Exception as exc:
        logger.warning(
            "optional_chain_enqueue_failed",
            audit_log_id=str(audit_log.id),
            error_type=type(exc).__name__,
        )


async def _insert_validate_audit_log(
    tenant_id: UUID,
    user_id: str | None,
    prompt: str,
    evaluation: GuardrailEvaluation,
    latency_ms: int,
    request: Request,
) -> None:
    """Write validate endpoint telemetry into audit logs, with retry on transient failure."""
    action = evaluation.action
    user_agent = request.headers.get("user-agent")

    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as db:
                log = _build_audit_log(
                    tenant_id=tenant_id,
                    session_id=user_id,
                    hook_type="access",
                    message=prompt,
                    evaluation=evaluation,
                    processing_ms=latency_ms,
                    user_agent=user_agent,
                )
                log.details = {
                    **(log.details or {}),
                    "endpoint_called": "/api/v1/validate",
                }
                db.add(log)
                await db.commit()
            return
        except Exception as exc:
            if attempt == 2:
                logger.error(
                    "validate_audit_insert_failed",
                    tenant_id=str(tenant_id),
                    action=action,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
            else:
                logger.warning(
                    "validate_audit_insert_retry",
                    tenant_id=str(tenant_id),
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(2**attempt)


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
    tenant_id, policy_version = _freeze_guardrail_request_context(tenant)
    config = await _get_safety_config(db, tenant_id)
    evaluation = await evaluate_guardrails(
        db,
        tenant_id,
        policy_version,
        config,
        body.prompt,
    )

    latency_ms = int((time.monotonic() - start) * 1000)
    if trace_enabled:
        emit_timing(
            "perf.validate.total",
            tenant_id=str(tenant_id),
            elapsed_ms=latency_ms,
            action=evaluation.action,
            status=evaluation.status,
            violations=[item["type"] for item in evaluation.violations],
        )
    background_tasks.add_task(
        _insert_validate_audit_log,
        tenant_id,
        body.user_id,
        body.prompt,
        evaluation,
        latency_ms,
        request,
    )

    return ValidateResponse(
        action=evaluation.action,
        reason=evaluation.reason,
        redacted_text=(
            evaluation.safe_text
            if evaluation.redaction_counts
            else None
        ),
        evaluation_status=evaluation.status,
        error_code=evaluation.error_code,
        evaluation_failures=list(evaluation.failure_codes),
    )


@router.post("/check", response_model=CheckResponse)
@limiter.limit("100/minute")
async def check_message(
    body: CheckRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> CheckResponse:
    """Run all configured safety checks and return a guardrail decision."""
    start = time.monotonic()
    trace_enabled = should_trace()
    tenant_id, policy_version = _freeze_guardrail_request_context(tenant)
    config = await _get_safety_config(db, tenant_id)
    evaluation = await evaluate_guardrails(
        db,
        tenant_id,
        policy_version,
        config,
        body.message,
    )

    processing_ms = int((time.monotonic() - start) * 1000)
    if trace_enabled:
        emit_timing(
            "perf.check.total",
            tenant_id=str(tenant_id),
            elapsed_ms=processing_ms,
            action=_audit_action(evaluation),
            status=evaluation.status,
        )
    action = _audit_action(evaluation)
    audit_log = _build_audit_log(
        tenant_id=tenant_id,
        session_id=body.session_id,
        hook_type="pre_execution" if action == "BLOCKED" else "post_execution",
        message=body.message,
        evaluation=evaluation,
        processing_ms=processing_ms,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    _enqueue_chain_best_effort(audit_log, evaluation)

    if action == "BLOCKED":
        sanitized_message = evaluation.fallback_message
    elif evaluation.status == "evaluation_failed" and evaluation.fail_mode == "closed":
        sanitized_message = evaluation.fallback_message
    elif evaluation.status == "redacted" or evaluation.status == "evaluation_failed":
        sanitized_message = evaluation.safe_text
    else:
        sanitized_message = None

    return CheckResponse(
        action=action,
        original_message=None,
        sanitized_message=sanitized_message,
        violations=_response_violations(evaluation),
        processing_ms=processing_ms,
        audit_id=audit_log.id,
        evaluation_status=evaluation.status,
        error_code=evaluation.error_code,
        evaluation_failures=list(evaluation.failure_codes),
    )


@router.post("/sanitize", response_model=SanitizeResponse)
@limiter.limit("100/minute")
async def sanitize_message(
    body: SanitizeRequest,
    request: Request,
    tenant: Tenant = Depends(get_tenant_by_api_key),
    db: AsyncSession = Depends(get_db),
) -> SanitizeResponse:
    """Run the shared safety pipeline before returning sanitized text."""
    start = time.monotonic()
    trace_enabled = should_trace()
    tenant_id, policy_version = _freeze_guardrail_request_context(tenant)
    config = await _get_safety_config(db, tenant_id)
    evaluation = await evaluate_guardrails(
        db,
        tenant_id,
        policy_version,
        config,
        body.message,
    )
    processing_ms = int((time.monotonic() - start) * 1000)
    if trace_enabled:
        emit_timing(
            "perf.sanitize.total",
            tenant_id=str(tenant_id),
            elapsed_ms=processing_ms,
            action=_audit_action(evaluation),
            status=evaluation.status,
        )

    action = _audit_action(evaluation)
    audit_log = _build_audit_log(
        tenant_id=tenant_id,
        session_id=body.session_id,
        hook_type="pre_execution" if action == "BLOCKED" else "post_execution",
        message=body.message,
        evaluation=evaluation,
        processing_ms=processing_ms,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    _enqueue_chain_best_effort(audit_log, evaluation)

    if action == "BLOCKED":
        sanitized_message = evaluation.fallback_message
    elif evaluation.status == "evaluation_failed" and evaluation.fail_mode == "closed":
        sanitized_message = evaluation.fallback_message
    else:
        sanitized_message = evaluation.safe_text or ""

    return SanitizeResponse(
        sanitized_message=sanitized_message,
        redactions=[
            {"type": pii_type, "count": count}
            for pii_type, count in evaluation.redaction_counts.items()
        ],
        processing_ms=processing_ms,
        audit_id=audit_log.id,
        action=action,
        evaluation_status=evaluation.status,
        error_code=evaluation.error_code,
        evaluation_failures=list(evaluation.failure_codes),
    )
