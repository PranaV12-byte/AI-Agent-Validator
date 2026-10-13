"""Authenticated protected-chat demo and provider setup status."""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_client import get_redis
from app.database import MANUAL_COMMIT_REQUEST_STATE_KEY, get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.schemas.protected_chat import (
    ProtectedChatReadiness,
    ProtectedChatRequest,
    ProtectedChatResponse,
)
from app.services.guardrails.audit_safety import (
    make_safe_audit_evidence,
    pseudonymize_audit_identifier,
    sanitize_audit_metadata,
)
from app.services.guardrails.groq_client import (
    FREE_LISTED_MODEL_IDS,
    groq_client,
)
from app.services.guardrails.pipeline import GuardrailEvaluation, GuardrailSnapshot
from app.services.guardrails.protected_chat import run_protected_chat

router = APIRouter(prefix="/demo/protected-chat", tags=["Protected chat demo"])
logger = structlog.get_logger()


async def _mark_manual_audit_commits(request: Request) -> None:
    """Mark the shared auth/route session for explicit, bounded audit commits."""
    setattr(request.state, MANUAL_COMMIT_REQUEST_STATE_KEY, True)


def _readiness_error() -> str | None:
    """Describe local provider setup without exposing or testing credentials."""
    if not settings.groq_api_key.strip():
        return "groq_api_key_missing"
    if not settings.groq_live_enabled:
        return "groq_live_disabled"
    if not settings.groq_free_plan_confirmed:
        return "groq_free_plan_unconfirmed"
    if settings.groq_model.strip() not in FREE_LISTED_MODEL_IDS:
        return "groq_model_not_allowlisted"
    return None


@router.get("/readiness", response_model=ProtectedChatReadiness)
async def get_protected_chat_readiness(
    _tenant: Tenant = Depends(get_current_tenant),
) -> ProtectedChatReadiness:
    error_code = _readiness_error()
    return ProtectedChatReadiness(
        ready=error_code is None,
        error_code=error_code,
        model=settings.groq_model.strip(),
    )


def _new_audit_log(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    stage: str,
    text: str,
    evaluation: GuardrailEvaluation | None,
    error_code: str | None,
    snapshot: GuardrailSnapshot,
    processing_ms: int,
    user_agent: str | None,
) -> AuditLog:
    evidence = make_safe_audit_evidence(text)
    pseudonym = pseudonymize_audit_identifier(
        str(conversation_id),
        namespace=f"session:{tenant_id}",
    )
    if evaluation is not None:
        from app.api.v1.hooks import _build_audit_log

        record = _build_audit_log(
            tenant_id=tenant_id,
            session_id=str(conversation_id),
            hook_type="protected_chat_pre" if stage == "pre" else "protected_chat_post",
            message=text,
            evaluation=evaluation,
            processing_ms=processing_ms,
            user_agent=user_agent,
        )
        if evaluation.status == "evaluation_failed":
            record.action = "ERROR"
    else:
        record = AuditLog(
            tenant_id=tenant_id,
            session_id=pseudonym,
            hook_type="protected_chat_post",
            action="ERROR",
            violation_type="provider_error",
            severity="high",
            input_preview=evidence.input_preview,
            payload_hash=evidence.payload_hash,
            policy_version=snapshot.policy_version,
            processing_ms=processing_ms,
            ip_address=None,
            user_agent=sanitize_audit_metadata(user_agent),
            details={
                "evaluation_status": "provider_unavailable",
                "error_code": error_code,
                "evaluation_failures": [],
                "redaction_counts": evidence.redaction_counts,
                "policy_version": snapshot.policy_version,
                "policy_snapshot_hash": snapshot.policy_snapshot_hash,
            },
        )

    record.details = {
        **(record.details or {}),
        "protected_chat": True,
        "stage": stage,
        "conversation_id": pseudonym,
        "evaluation_status": (
            evaluation.status if evaluation is not None else "provider_unavailable"
        ),
        "error_code": error_code or (
            evaluation.error_code if evaluation is not None else None
        ),
        "evaluation_failures": (
            list(evaluation.failure_codes) if evaluation is not None else []
        ),
        "policy_version": snapshot.policy_version,
        "policy_snapshot_hash": snapshot.policy_snapshot_hash,
    }
    return record


@router.post(
    "",
    response_model=ProtectedChatResponse,
    dependencies=[Depends(_mark_manual_audit_commits)],
)
async def protected_chat(
    body: ProtectedChatRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> ProtectedChatResponse | JSONResponse:
    """Run a pre-check, one generation, and a post-check before returning text."""
    tenant_id = UUID(str(tenant.id))
    policy_version = int(tenant.active_policy_version)
    conversation_id = uuid4()

    try:
        redis = await get_redis()
        lock = redis.lock(
            f"safebot:protected-chat:inflight:{tenant_id}",
            timeout=90,
            blocking_timeout=0,
        )
        acquired = await lock.acquire(blocking=False)
    except Exception as exc:
        logger.warning(
            "protected_chat_lock_unavailable",
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content=ProtectedChatResponse(
                conversation_id=conversation_id,
                status="service_unavailable",
                fallback_message="The protected demo is temporarily unavailable. Please try again.",
                error_code="inflight_guard_unavailable",
                policy_version=policy_version,
            ).model_dump(mode="json"),
        )

    if not acquired:
        return JSONResponse(
            status_code=409,
            content=ProtectedChatResponse(
                conversation_id=conversation_id,
                status="busy",
                fallback_message="A protected request is already in progress for this account.",
                error_code="protected_chat_busy",
                policy_version=policy_version,
            ).model_dump(mode="json"),
        )

    audit_ids: list[UUID] = []

    async def write_audit(
        stage: str,
        text: str,
        evaluation: GuardrailEvaluation | None,
        error_code: str | None,
        snapshot: GuardrailSnapshot,
        processing_ms: int,
    ) -> UUID:
        record = _new_audit_log(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            stage=stage,
            text=text,
            evaluation=evaluation,
            error_code=error_code,
            snapshot=snapshot,
            processing_ms=processing_ms,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        audit_ids.append(record.id)
        return record.id

    try:
        outcome = await run_protected_chat(
            db=db,
            tenant_id=tenant_id,
            tenant_policy_version=policy_version,
            message=body.message,
            write_audit=write_audit,
            client=groq_client,
        )
    except Exception as exc:
        logger.error(
            "protected_chat_failed",
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content=ProtectedChatResponse(
                conversation_id=conversation_id,
                status="service_unavailable",
                fallback_message="The protected demo is temporarily unavailable. Please try again.",
                error_code="protected_chat_unavailable",
                policy_version=policy_version,
                audit_ids=audit_ids,
            ).model_dump(mode="json"),
        )
    finally:
        try:
            await lock.release()
        except Exception:
            logger.warning(
                "protected_chat_lock_release_failed",
                tenant_id=str(tenant_id),
            )

    response = ProtectedChatResponse(
        conversation_id=conversation_id,
        status=outcome.status,
        answer=outcome.answer,
        fallback_message=outcome.fallback_message,
        error_code=outcome.error_code,
        input_redacted=outcome.input_redacted,
        output_redacted=outcome.output_redacted,
        policy_version=outcome.policy_version,
        audit_ids=audit_ids,
    )
    status_code = {
        "provider_unavailable": 503,
        "service_unavailable": 503,
        "evaluation_failed": 503,
        "busy": 409,
    }.get(outcome.status, 200)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))
    return response
