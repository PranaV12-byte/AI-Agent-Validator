"""Audit log endpoints."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.schemas.audit import AuditListResponse, AuditLogResponse
from app.services.guardrails.audit_safety import (
    pseudonymize_audit_identifier,
    sanitize_audit_metadata,
)

router = APIRouter(prefix="/audit", tags=["Audit Logs"])

_PSEUDONYMIZED_ID = re.compile(r"^id_[0-9a-f]{32}$", re.IGNORECASE)
_SENSITIVE_DETAIL_LABEL = (
    r"authorization|cookie|password|passwd|secret|credential|credentials|"
    r"api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|"
    r"auth[\s_-]*token|client[\s_-]*secret|private[\s_-]*key|mnemonic|token"
)
_SENSITIVE_DETAIL_KEY = re.compile(
    rf"(?:^|[_\-.])(?:{_SENSITIVE_DETAIL_LABEL})(?:$|[_\-.])",
    re.IGNORECASE,
)
_SENSITIVE_LABELLED_VALUE = re.compile(
    rf"(?ix)(?P<label>[\"']?\b(?:{_SENSITIVE_DETAIL_LABEL})\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"?|\'[^\']*\'?|[^\s,;}\]\r\n]+)"
)
_MAX_DETAIL_DEPTH = 5
_MAX_DETAIL_ITEMS = 100
_MAX_DETAIL_CHARS = 8192
_MAX_DETAIL_STRING_CHARS = 512
_OMITTED = "[OMITTED]"


@dataclass
class _DetailBudget:
    """One shared traversal and text budget for a single audit row."""

    items_remaining: int = _MAX_DETAIL_ITEMS
    chars_remaining: int = _MAX_DETAIL_CHARS
    chars_exhausted: bool = False


def _safe_display_text(value: str | None, *, max_length: int) -> tuple[str | None, bool]:
    """Sanitize stored text and suppress even short values after credential labels."""
    safe_text = sanitize_audit_metadata(value, max_length=max_length)
    if safe_text is None:
        return None, value is not None
    safe_text = _SENSITIVE_LABELLED_VALUE.sub(
        lambda match: f"{match.group('label')}[SECRET_REDACTED]",
        safe_text,
    )
    return safe_text, safe_text != value or len(value or "") > max_length


def _omitted_detail_value(budget: _DetailBudget) -> tuple[Any, bool]:
    """Emit one bounded omission marker and charge it to the shared text budget."""
    if budget.chars_remaining < len(_OMITTED):
        budget.chars_exhausted = True
        return None, True
    budget.chars_remaining -= len(_OMITTED)
    return _OMITTED, True


def _safe_detail_value(
    value: Any,
    budget: _DetailBudget,
    depth: int = 0,
) -> tuple[Any, bool]:
    """Return a sanitized copy within shared per-row depth, item, and text caps."""
    if budget.items_remaining <= 0:
        return None, True
    budget.items_remaining -= 1
    if depth >= _MAX_DETAIL_DEPTH:
        return _omitted_detail_value(budget)

    if isinstance(value, str):
        if len(value) > _MAX_DETAIL_STRING_CHARS:
            return _omitted_detail_value(budget)
        if len(value) > budget.chars_remaining:
            budget.chars_exhausted = True
            return _omitted_detail_value(budget)
        safe_value, changed = _safe_display_text(
            value,
            max_length=min(_MAX_DETAIL_STRING_CHARS, budget.chars_remaining),
        )
        if safe_value is None:
            return _omitted_detail_value(budget)
        if len(safe_value) > budget.chars_remaining:
            budget.chars_exhausted = True
            return _omitted_detail_value(budget)
        budget.chars_remaining -= len(safe_value)
        return safe_value, changed

    if isinstance(value, dict):
        safe_dict: dict[str, Any] = {}
        changed = False
        omitted_keys = 0
        for index, (key, child) in enumerate(value.items()):
            if budget.items_remaining <= 0 or budget.chars_exhausted or budget.chars_remaining <= 0:
                changed = True
                break
            # Count key processing as traversal work too. A dict of only
            # sensitive fields must not bypass the shared item budget merely
            # because its values are redacted without recursive traversal.
            budget.items_remaining -= 1
            if not isinstance(key, str):
                omitted_keys += 1
                changed = True
                continue
            # Do not display truncated attacker-controlled keys: a credential
            # label beyond the display cap could otherwise be missed while its
            # value is still emitted as ordinary data.
            if len(key) > 80:
                omitted_keys += 1
                changed = True
                continue
            safe_key, key_changed = _safe_display_text(key, max_length=80)
            if not safe_key:
                omitted_keys += 1
                changed = True
                continue
            if len(safe_key) > budget.chars_remaining:
                budget.chars_exhausted = True
                changed = True
                break
            budget.chars_remaining -= len(safe_key)
            normalized_key = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])", "_", safe_key
            ).lower()
            normalized_key = re.sub(r"[\s-]+", "_", normalized_key)
            if _SENSITIVE_DETAIL_KEY.search(normalized_key):
                if len("[REDACTED]") > budget.chars_remaining:
                    safe_value, _ = _omitted_detail_value(budget)
                    safe_dict[safe_key] = safe_value
                    changed = True
                    continue
                safe_dict[safe_key] = "[REDACTED]"
                budget.chars_remaining -= len("[REDACTED]")
                if budget.chars_remaining == 0:
                    budget.chars_exhausted = True
                changed = True
                continue
            safe_child, child_changed = _safe_detail_value(child, budget, depth + 1)
            if safe_key in safe_dict:
                safe_key = f"{safe_key}_{index}"
                changed = True
            safe_dict[safe_key] = safe_child
            changed = changed or key_changed or safe_key != key or child_changed
        if omitted_keys:
            marker_cost = len("_omitted_items") + len(str(omitted_keys))
            if budget.items_remaining > 0 and marker_cost <= budget.chars_remaining:
                budget.items_remaining -= 1
                budget.chars_remaining -= marker_cost
                safe_dict["_omitted_items"] = omitted_keys
            else:
                changed = True
        return safe_dict, changed

    if isinstance(value, (list, tuple)):
        safe_items = []
        changed = False
        for item in value:
            if budget.items_remaining <= 0 or budget.chars_exhausted or budget.chars_remaining <= 0:
                changed = True
                break
            safe_item, item_changed = _safe_detail_value(item, budget, depth + 1)
            safe_items.append(safe_item)
            changed = changed or item_changed
        if len(safe_items) < len(value) and not changed:
            changed = True
        return safe_items, changed

    if value is None or isinstance(value, (bool, int, float)):
        scalar_length = len(str(value))
        if scalar_length > budget.chars_remaining:
            budget.chars_exhausted = True
            return _omitted_detail_value(budget)
        budget.chars_remaining -= scalar_length
        return value, False
    return None, True


def _anchoring_view(tx_id: str | None) -> tuple[str | None, str]:
    if tx_id and tx_id.lower().startswith("mock_tx_"):
        return None, "not_anchored"
    if tx_id:
        return tx_id, "anchored"
    if settings.algorand_app_id == 0:
        return None, "disabled"
    return None, "pending"


def _audit_log_view(log: AuditLog) -> AuditLogResponse:
    """Build a safe API view without mutating stored audit evidence."""
    redacted_fields: set[str] = set()

    safe_preview, preview_changed = _safe_display_text(log.input_preview, max_length=200)
    if preview_changed:
        redacted_fields.add("input_preview")

    safe_details, details_changed = _safe_detail_value(log.details or {}, _DetailBudget())
    if not isinstance(safe_details, dict):
        safe_details = {}
        details_changed = True
    if details_changed:
        redacted_fields.add("details")

    safe_session_id = log.session_id
    if safe_session_id and not _PSEUDONYMIZED_ID.fullmatch(safe_session_id):
        safe_session_id = pseudonymize_audit_identifier(
            safe_session_id,
            namespace=f"session:{log.tenant_id}",
        )
        redacted_fields.add("session_id")

    safe_ip_address = None
    if log.ip_address is not None:
        safe_ip_address = pseudonymize_audit_identifier(
            str(log.ip_address),
            namespace=f"ip:{log.tenant_id}",
        )
        redacted_fields.add("ip_address")

    safe_user_agent, user_agent_changed = _safe_display_text(log.user_agent, max_length=256)
    if user_agent_changed:
        redacted_fields.add("user_agent")

    safe_tx_id, anchoring_status = _anchoring_view(log.algorand_tx_id)
    return AuditLogResponse.model_validate(
        {
            "id": log.id,
            "tenant_id": log.tenant_id,
            "session_id": safe_session_id,
            "hook_type": log.hook_type,
            "action": log.action,
            "violation_type": log.violation_type,
            "severity": log.severity,
            "input_preview": safe_preview,
            "details": safe_details,
            # Preserve the stored value; it remains the historical hash, not a
            # hash recomputed from this newly sanitized display view.
            "payload_hash": log.payload_hash,
            "payload_hash_provenance": (
                "stored_unverified" if log.payload_hash else "unavailable"
            ),
            "policy_version": log.policy_version,
            "algorand_tx_id": safe_tx_id,
            "processing_ms": log.processing_ms,
            "ip_address": safe_ip_address,
            "user_agent": safe_user_agent,
            "created_at": log.created_at,
            "redacted_fields": sorted(redacted_fields),
            "anchoring_status": anchoring_status,
        }
    )


def _csv_safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    leading = text.lstrip(" \t\r\n\ufeff")
    if text.startswith(("\t", "\r", "\n")) or (leading and leading[0] in "=+-@"):
        return "'" + text
    return text


@router.get("/", response_model=AuditListResponse)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None, description="Filter logs on or after this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Filter logs on or before this date (YYYY-MM-DD)"),
    search: str | None = Query(None, max_length=500, description="Filter by input_preview content (case-insensitive)"),
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
    logs = [_audit_log_view(log) for log in rows.scalars().all()]

    page = offset // limit + 1

    return AuditListResponse(logs=logs, total=total, page=page, page_size=limit)


EXPORT_CAP = 10_000

CSV_FIELDS = [
    "id", "created_at", "action", "violation_type", "severity",
    "hook_type", "input_preview", "processing_ms", "policy_version",
    "payload_hash", "payload_hash_provenance", "algorand_tx_id",
    "anchoring_status", "redacted_fields",
    "session_id", "ip_address",
]


@router.get("/export")
async def export_audit_logs(
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    search: str | None = Query(None, max_length=500),
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
    logs = [_audit_log_view(log) for log in rows.scalars().all()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_FIELDS)

    for log in logs:
        writer.writerow(_csv_safe_cell(value) for value in [
            str(log.id),
            log.created_at.isoformat() if log.created_at else "",
            log.action or "",
            log.violation_type or "",
            log.severity or "",
            log.hook_type or "",
            log.input_preview or "",
            log.processing_ms or "",
            log.policy_version or "",
            log.payload_hash or "",
            log.payload_hash_provenance,
            log.algorand_tx_id or "",
            log.anchoring_status,
            ",".join(log.redacted_fields),
            log.session_id or "",
            str(log.ip_address) if log.ip_address else "",
        ])

    output.seek(0)
    response_headers: dict[str, str] = {
        "Content-Disposition": 'attachment; filename="safebot-audit-export.csv"',
    }
    if total > EXPORT_CAP:
        response_headers["X-Safebot-Truncated"] = f"true; total={total}; exported={EXPORT_CAP}"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers=response_headers,
    )
