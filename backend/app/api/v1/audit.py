"""Audit log endpoints."""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.schemas.audit import AuditListResponse, AuditLogResponse

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/", response_model=AuditListResponse)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None, description="Filter logs on or after this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Filter logs on or before this date (YYYY-MM-DD)"),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    """Return recent tenant audit logs ordered by newest first."""
    base_filter = [AuditLog.tenant_id == tenant.id]

    if action:
        base_filter.append(AuditLog.action == action)

    if start_date:
        base_filter.append(
            AuditLog.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        )

    if end_date:
        base_filter.append(
            AuditLog.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        )

    count_result = await db.execute(select(func.count()).select_from(AuditLog).where(*base_filter))
    total = count_result.scalar_one()

    rows = await db.execute(
        select(AuditLog)
        .where(*base_filter)
        .order_by(desc(AuditLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    logs = rows.scalars().all()

    page = offset // limit + 1

    return AuditListResponse(logs=logs, total=total, page=page, page_size=limit)
