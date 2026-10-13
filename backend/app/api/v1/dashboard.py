"""Dashboard stats and safety-config endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, and_, case, cast, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.dashboard import (
    DashboardDailyActivity,
    DashboardResponse,
    SafetyConfigResponse,
    SafetyConfigUpdate,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return last-7-days dashboard aggregates for authenticated tenant."""
    now_utc = datetime.now(timezone.utc)
    start_date = now_utc.date() - timedelta(days=6)
    seven_days_ago = now_utc.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=6)

    evaluation_status = AuditLog.details["evaluation_status"].astext
    evaluation_failures = AuditLog.details["evaluation_failures"].astext
    has_evaluation_error = func.coalesce(
        or_(
            AuditLog.action == "ERROR",
            evaluation_status == "evaluation_failed",
            and_(
                evaluation_failures.is_not(None),
                evaluation_failures != "[]",
            ),
        ),
        False,
    )
    affirmative_violation = or_(
        AuditLog.details["violations"].contains([{"type": "global_block"}]),
        AuditLog.details["violations"].contains([{"type": "prompt_injection"}]),
        AuditLog.details["violations"].contains([{"type": "policy_violation"}]),
    )
    is_protected_chat_log = func.coalesce(
        AuditLog.details["protected_chat"].astext == "true",
        False,
    )
    audit_stage = AuditLog.details["stage"].astext
    successful_stage = AuditLog.action.in_(("ALLOWED", "REDACTED"))
    terminal_success_log = or_(
        and_(
            is_protected_chat_log,
            audit_stage == "post",
            successful_stage,
            evaluation_status.in_(("allowed", "redacted")),
        ),
        and_(not_(is_protected_chat_log), successful_stage),
    )
    is_blocked_log = or_(
        affirmative_violation,
        and_(AuditLog.action == "BLOCKED", not_(has_evaluation_error)),
    )
    conversation_key = case(
        (
            AuditLog.details["protected_chat"].astext == "true",
            AuditLog.details["conversation_id"].astext,
        ),
        else_=cast(AuditLog.id, String),
    )
    conversations = (
        select(
            conversation_key.label("conversation_key"),
            func.bool_or(is_protected_chat_log).label("is_protected_chat"),
            func.bool_or(is_blocked_log).label("is_blocked"),
            func.bool_or(has_evaluation_error).label("has_error"),
            func.bool_or(AuditLog.action == "REDACTED").label("was_redacted"),
            func.bool_or(terminal_success_log).label("has_terminal_success"),
            func.sum(AuditLog.processing_ms).label("total_latency_ms"),
            func.min(AuditLog.created_at).label("first_seen_at"),
        )
        .where(
            AuditLog.tenant_id == tenant.id,
            AuditLog.created_at >= seven_days_ago,
            AuditLog.created_at <= now_utc,
        )
        .group_by(conversation_key)
        .subquery()
    )
    blocked = conversations.c.is_blocked.is_(True)
    completed = conversations.c.has_terminal_success.is_(True)
    errored = and_(
        not_(blocked),
        or_(
            conversations.c.has_error.is_(True),
            and_(
                conversations.c.is_protected_chat.is_(True),
                not_(completed),
            ),
        ),
    )
    redacted = and_(
        not_(blocked),
        not_(errored),
        completed,
        conversations.c.was_redacted.is_(True),
    )
    allowed = and_(
        not_(blocked),
        not_(errored),
        completed,
        not_(redacted),
    )
    other_error = and_(not_(blocked), not_(errored), not_(redacted), not_(allowed))
    utc_date = func.date(func.timezone("UTC", conversations.c.first_seen_at))
    daily_summary = await db.execute(
        select(
            utc_date.label("date"),
            func.count().label("total_requests"),
            func.sum(case((allowed, 1), else_=0)).label("allowed_requests"),
            func.sum(case((redacted, 1), else_=0)).label("redacted_requests"),
            func.sum(case((blocked, 1), else_=0)).label("blocked_requests"),
            func.sum(case((or_(errored, other_error), 1), else_=0)).label("error_requests"),
            func.sum(conversations.c.total_latency_ms).label("total_latency_ms"),
            func.count(conversations.c.total_latency_ms).label("latency_conversation_count"),
        )
        .select_from(conversations)
        .group_by(utc_date)
        .order_by(utc_date)
    )
    daily_rows = daily_summary.all()
    daily_by_date = {
        day.date: {
            "allowed_requests": int(day.allowed_requests or 0),
            "redacted_requests": int(day.redacted_requests or 0),
            "blocked_requests": int(day.blocked_requests or 0),
            "error_requests": int(day.error_requests or 0),
        }
        for day in daily_rows
    }
    totals = {
        field: sum(day[field] for day in daily_by_date.values())
        for field in (
            "allowed_requests",
            "redacted_requests",
            "blocked_requests",
            "error_requests",
        )
    }
    total_requests = sum(int(day.total_requests or 0) for day in daily_rows)
    total_latency_ms = sum(int(day.total_latency_ms or 0) for day in daily_rows)
    latency_conversation_count = sum(
        int(day.latency_conversation_count or 0) for day in daily_rows
    )
    avg_latency_ms = (
        total_latency_ms / latency_conversation_count
        if latency_conversation_count
        else 0.0
    )
    daily_trend = [
        DashboardDailyActivity(
            date=day,
            **daily_by_date.get(
                day,
                {
                    "allowed_requests": 0,
                    "redacted_requests": 0,
                    "blocked_requests": 0,
                    "error_requests": 0,
                },
            ),
        )
        for day in (start_date + timedelta(days=offset) for offset in range(7))
    ]

    return DashboardResponse(
        total_requests=total_requests,
        blocked_requests=totals["blocked_requests"],
        allowed_requests=totals["allowed_requests"],
        redacted_requests=totals["redacted_requests"],
        error_requests=totals["error_requests"],
        avg_latency_ms=round(avg_latency_ms, 1),
        daily_trend=daily_trend,
    )


@router.get("/safety-config", response_model=SafetyConfigResponse)
async def get_safety_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SafetyConfigResponse:
    """Return tenant-specific safety configuration."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Safety config not found")
    return config


@router.put("/safety-config", response_model=SafetyConfigResponse)
async def update_safety_config(
    body: SafetyConfigUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SafetyConfigResponse:
    """Update tenant safety configuration fields."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Safety config not found")

    update_data = body.model_dump(exclude_unset=True)
    enforcement_fields = {
        "global_block_enabled",
        "injection_protection",
        "injection_sensitivity",
        "pii_redaction",
        "pii_types",
        "policy_enforcement",
        "fail_mode",
        "fallback_message",
    }
    if "global_block_enabled" in update_data:
        config.global_block_enabled = update_data["global_block_enabled"]
    if "injection_protection" in update_data:
        config.injection_protection = update_data["injection_protection"]
    if "injection_sensitivity" in update_data:
        config.injection_sensitivity = update_data["injection_sensitivity"]
    if "pii_redaction" in update_data:
        config.pii_redaction = update_data["pii_redaction"]
    if "pii_types" in update_data:
        config.pii_types = update_data["pii_types"]
    if "policy_enforcement" in update_data:
        config.policy_enforcement = update_data["policy_enforcement"]
    if "fail_mode" in update_data:
        config.fail_mode = update_data["fail_mode"]
    if "fallback_message" in update_data:
        config.fallback_message = update_data["fallback_message"]
    if "log_retention_days" in update_data:
        config.log_retention_days = update_data["log_retention_days"]

    if enforcement_fields.intersection(update_data):
        tenant.active_policy_version += 1

    await db.commit()
    await db.refresh(config)
    return config
