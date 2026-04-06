"""Audit log endpoints."""

import csv
import io
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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
    search: str | None = Query(None, description="Filter by input_preview content (case-insensitive)"),
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

    if search:
        base_filter.append(AuditLog.input_preview.ilike(f"%{search}%"))

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


EXPORT_CAP = 10_000

CSV_FIELDS = [
    "id", "created_at", "action", "violation_type", "severity",
    "hook_type", "input_preview", "processing_ms", "policy_version",
    "algorand_tx_id", "session_id", "ip_address",
]


@router.get("/export")
async def export_audit_logs(
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    search: str | None = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream a CSV export of audit logs (capped at 10 000 rows)."""
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
    if search:
        base_filter.append(AuditLog.input_preview.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(AuditLog).where(*base_filter))
    total = count_result.scalar_one()

    rows = await db.execute(
        select(AuditLog)
        .where(*base_filter)
        .order_by(desc(AuditLog.created_at))
        .limit(EXPORT_CAP)
    )
    logs = rows.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_FIELDS)
    if total > EXPORT_CAP:
        writer.writerow([f"# Truncated to {EXPORT_CAP} rows (total: {total})"] + [""] * (len(CSV_FIELDS) - 1))

    for log in logs:
        writer.writerow([
            str(log.id),
            log.created_at.isoformat() if log.created_at else "",
            log.action or "",
            log.violation_type or "",
            log.severity or "",
            log.hook_type or "",
            log.input_preview or "",
            log.processing_ms or "",
            log.policy_version or "",
            log.algorand_tx_id or "",
            log.session_id or "",
            str(log.ip_address) if log.ip_address else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="safebot-audit-export.csv"'},
    )
