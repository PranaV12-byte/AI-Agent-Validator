"""Dashboard stats and safety-config endpoints."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.policy import Policy
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.dashboard import (
    DashboardResponse,
    DashboardStats,
    SafetyConfigResponse,
    SafetyConfigUpdate,
    UsageTrend,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return today's metrics and 30-day trend data for dashboard."""
    today = date.today()

    today_query = select(
        func.count(AuditLog.id).label("total"),
        func.count(AuditLog.id).filter(AuditLog.action == "BLOCKED").label("blocked"),
        func.count(AuditLog.id).filter(AuditLog.action == "ALLOWED").label("allowed"),
        func.count(AuditLog.id).filter(AuditLog.action == "REDACTED").label("redacted"),
        func.avg(AuditLog.processing_ms).label("avg_latency"),
        func.count(AuditLog.algorand_tx_id).label("chain_verified"),
    ).where(
        AuditLog.tenant_id == tenant.id,
        func.date(AuditLog.created_at) == today,
    )

    result = await db.execute(today_query)
    row = result.one()
    total_today = row.total or 0
    blocked_today = row.blocked or 0

    policy_count = await db.execute(
        select(func.count(Policy.id)).where(
            Policy.tenant_id == tenant.id,
            Policy.is_enabled.is_(True),
        )
    )
    active_policies = policy_count.scalar() or 0

    stats = DashboardStats(
        total_requests_today=total_today,
        blocked_today=blocked_today,
        allowed_today=row.allowed or 0,
        redacted_today=row.redacted or 0,
        block_rate_percent=round(
            (blocked_today / total_today * 100) if total_today > 0 else 0, 1
        ),
        avg_latency_ms=round(float(row.avg_latency or 0), 1),
        active_policies=active_policies,
        chain_verified_count=row.chain_verified or 0,
    )

    thirty_days_ago = today - timedelta(days=30)
    trends_query = (
        select(
            func.date(AuditLog.created_at).label("log_date"),
            func.count(AuditLog.id).label("total"),
            func.count(AuditLog.id)
            .filter(AuditLog.action == "BLOCKED")
            .label("blocked"),
            func.count(AuditLog.id)
            .filter(AuditLog.action == "ALLOWED")
            .label("allowed"),
            func.count(AuditLog.id)
            .filter(AuditLog.action == "REDACTED")
            .label("redacted"),
            func.avg(AuditLog.processing_ms).label("avg_lat"),
        )
        .where(
            AuditLog.tenant_id == tenant.id,
            func.date(AuditLog.created_at) >= thirty_days_ago,
        )
        .group_by(func.date(AuditLog.created_at))
        .order_by(func.date(AuditLog.created_at))
    )

    trends_result = await db.execute(trends_query)
    trends = [
        UsageTrend(
            date=row_item.log_date,
            total_requests=row_item.total,
            blocked_count=row_item.blocked,
            allowed_count=row_item.allowed,
            redacted_count=row_item.redacted,
            avg_latency_ms=round(float(row_item.avg_lat or 0), 1),
        )
        for row_item in trends_result.all()
    ]

    return DashboardResponse(stats=stats, trends=trends)


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
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    return config
