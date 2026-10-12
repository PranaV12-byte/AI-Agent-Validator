"""Celery worker for async tasks: Algorand TX submission, report generation."""

import re
import structlog
from celery import Celery
from celery.signals import worker_shutdown
from sqlalchemy import create_engine

from app.config import settings

logger = structlog.get_logger()


def _safe_error_type(error: Exception) -> str:
    """Return bounded exception type metadata without provider error text."""
    return re.sub(r"[^A-Za-z0-9_]", "", type(error).__name__)[:64] or "UnknownError"


# Module-level singleton sync engine — created once, shared across all tasks.
# This prevents the connection pool leak that occurs when create_engine() is
# called on every task invocation.
_sync_engine = None


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
        _sync_engine = create_engine(sync_url)
    return _sync_engine


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Dispose the shared engine on worker shutdown to release DB connections."""
    global _sync_engine
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None

celery_app = Celery(
    "safebot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=30,
    task_max_retries=3,
    # Dead-letter queue: failed tasks are routed to a dedicated queue for inspection.
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "dead_letter": {"exchange": "dead_letter", "routing_key": "dead_letter"},
    },
    task_default_queue="default",
    # Periodic tasks (Celery Beat)
    beat_schedule={
        "purge-old-audit-logs": {
            "task": "purge_old_audit_logs",
            "schedule": 86400,  # Run daily (every 24 hours)
        },
    },
)


@celery_app.task(bind=True, name="submit_to_chain", max_retries=3)
def submit_to_chain_task(
    self,
    audit_log_id: str,
    action: str,
    violation_type: str,
    payload_hash: str,
) -> dict[str, str]:
    """Submit a violation/approval to the Algorand smart contract."""
    from app.services.algorand_writer import submit_audit_to_algorand

    retry_countdown = 30
    try:
        tx_id = submit_audit_to_algorand(
            audit_log_id,
            action,
            violation_type,
            payload_hash,
        )
        if tx_id is None:
            logger.info(
                "algorand_audit_submission_skipped",
                audit_log_id=audit_log_id,
                reason="chain_not_configured",
            )
            return {"status": "skipped", "reason": "chain_not_configured"}
        _update_audit_tx_id(audit_log_id, tx_id)
        return {"status": "success", "tx_id": tx_id}
    except Exception as exc:
        attempt = self.request.retries
        if attempt >= self.max_retries:
            logger.error(
                "algorand_submit_permanently_failed",
                audit_log_id=audit_log_id,
                error_code="chain_submission_failed",
                error_type=_safe_error_type(exc),
            )
            return {
                "status": "failed",
                "error_code": "chain_submission_failed",
                "error_type": _safe_error_type(exc),
            }
        countdown = 30 * (2 ** attempt)  # 30s, 60s, 120s
        retry_countdown = countdown

    # Retry outside the exception handler so Celery cannot retain a provider's
    # original exception message as chained context.
    raise self.retry(
        exc=RuntimeError("chain_submission_failed"),
        countdown=retry_countdown,
    ) from None


@celery_app.task(bind=True, name="register_policy_on_chain", max_retries=3)
def register_policy_on_chain_task(
    self,
    policy_id: str,
    policy_hash: str,
) -> dict[str, str]:
    """Register a policy hash on Algorand."""
    from app.services.algorand_writer import register_policy_on_algorand

    retry_countdown = 30
    try:
        tx_id = register_policy_on_algorand(policy_id, policy_hash)
        if tx_id is None:
            logger.info(
                "algorand_policy_registration_skipped",
                policy_id=policy_id,
                reason="chain_not_configured",
            )
            return {"status": "skipped", "reason": "chain_not_configured"}
        _update_policy_tx_id(policy_id, tx_id)
        return {"status": "success", "tx_id": tx_id}
    except Exception as exc:
        attempt = self.request.retries
        if attempt >= self.max_retries:
            logger.error(
                "algorand_policy_registration_permanently_failed",
                policy_id=policy_id,
                error_code="policy_registration_failed",
                error_type=_safe_error_type(exc),
            )
            return {
                "status": "failed",
                "error_code": "policy_registration_failed",
                "error_type": _safe_error_type(exc),
            }
        countdown = 30 * (2 ** attempt)
        retry_countdown = countdown

    # Retry outside the exception handler to keep the original provider error
    # and any response-body credentials out of Celery's chained traceback.
    raise self.retry(
        exc=RuntimeError("policy_registration_failed"),
        countdown=retry_countdown,
    ) from None


@celery_app.task(name="purge_old_audit_logs")
def purge_old_audit_logs_task() -> dict[str, int]:
    """
    Delete audit logs older than each tenant's log_retention_days setting.

    Uses batched deletes (1000 rows at a time) to avoid long table locks.
    Runs daily via Celery Beat.
    """
    from sqlalchemy import text

    engine = _get_sync_engine()
    total_deleted = 0

    with engine.connect() as conn:
        # Fetch all tenant IDs and their retention settings in one query.
        rows = conn.execute(
            text("SELECT tenant_id, log_retention_days FROM safety_configs")
        ).fetchall()

        for row in rows:
            tenant_id = str(row.tenant_id)
            retention_days = max(1, int(row.log_retention_days or 1))

            # Delete in batches to keep lock duration short.
            while True:
                result = conn.execute(
                    text("""
                        DELETE FROM audit_logs
                        WHERE id IN (
                            SELECT id FROM audit_logs
                            WHERE tenant_id = :tid
                              AND created_at < NOW() - INTERVAL '1 day' * :days
                            LIMIT 1000
                        )
                    """),
                    {"tid": tenant_id, "days": retention_days},
                )
                conn.commit()
                deleted = result.rowcount
                total_deleted += deleted
                if deleted < 1000:
                    break

    logger.info("audit_logs_purged", total_deleted=total_deleted)
    return {"deleted": total_deleted}


def _update_audit_tx_id(audit_log_id: str, tx_id: str) -> None:
    """Synchronous DB update inside Celery worker."""
    from sqlalchemy import text

    with _get_sync_engine().connect() as conn:
        conn.execute(
            text("UPDATE audit_logs SET algorand_tx_id = :tx_id WHERE id = :aid"),
            {"tx_id": tx_id, "aid": audit_log_id},
        )
        conn.commit()


def _update_policy_tx_id(policy_id: str, tx_id: str) -> None:
    """Synchronous DB update inside Celery worker."""
    from sqlalchemy import text

    with _get_sync_engine().connect() as conn:
        conn.execute(
            text("UPDATE policies SET algorand_tx_id = :tx_id WHERE id = :pid"),
            {"tx_id": tx_id, "pid": policy_id},
        )
        conn.commit()
