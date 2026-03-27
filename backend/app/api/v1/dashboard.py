"""Dashboard stats and safety-config endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.dashboard import (
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
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    query = select(
        func.count(AuditLog.id).label("total_requests"),
        func.count(AuditLog.id)
        .filter(AuditLog.action == "BLOCKED")
        .label("blocked_requests"),
        func.avg(AuditLog.processing_ms).label("avg_latency_ms"),
    ).where(
        AuditLog.tenant_id == tenant.id,
        AuditLog.created_at >= seven_days_ago,
    )

    result = await db.execute(query)
    row = result.one()

    return DashboardResponse(
        total_requests=int(row.total_requests or 0),
        blocked_requests=int(row.blocked_requests or 0),
        avg_latency_ms=round(float(row.avg_latency_ms or 0.0), 1),
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

    await db.commit()
    await db.refresh(config)
    return config
