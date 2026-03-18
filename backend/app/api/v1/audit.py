"""Audit log endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.schemas.audit import AuditListResponse

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/", response_model=AuditListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    """Return paginated audit logs for the authenticated tenant."""
    query = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    count_query = select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant.id)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = (
        query.order_by(desc(AuditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditListResponse(logs=logs, total=total, page=page, page_size=page_size)
