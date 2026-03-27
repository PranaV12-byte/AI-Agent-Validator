"""Celery worker for async tasks: Algorand TX submission, report generation."""

import structlog
from celery import Celery

from app.config import settings

logger = structlog.get_logger()

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

    try:
        tx_id = submit_audit_to_algorand(
            audit_log_id,
            action,
            violation_type,
            payload_hash,
        )
        _update_audit_tx_id(audit_log_id, tx_id)
        return {"status": "success", "tx_id": tx_id}
    except Exception as exc:
        attempt = self.request.retries
        if attempt >= self.max_retries:
            logger.error(
                "algorand_submit_permanently_failed",
                audit_log_id=audit_log_id,
                error=str(exc),
            )
            return {"status": "failed", "error": str(exc)}
        countdown = 30 * (2 ** attempt)  # 30s, 60s, 120s
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(bind=True, name="register_policy_on_chain", max_retries=3)
def register_policy_on_chain_task(
    self,
    policy_id: str,
    policy_hash: str,
) -> dict[str, str]:
    """Register a policy hash on Algorand."""
    from app.services.algorand_writer import register_policy_on_algorand

    try:
        tx_id = register_policy_on_algorand(policy_id, policy_hash)
        _update_policy_tx_id(policy_id, tx_id)
        return {"status": "success", "tx_id": tx_id}
    except Exception as exc:
        attempt = self.request.retries
        if attempt >= self.max_retries:
            logger.error(
                "algorand_policy_registration_permanently_failed",
                policy_id=policy_id,
                error=str(exc),
            )
            return {"status": "failed", "error": str(exc)}
        countdown = 30 * (2 ** attempt)
        raise self.retry(exc=exc, countdown=countdown)


def _update_audit_tx_id(audit_log_id: str, tx_id: str) -> None:
    """Synchronous DB update inside Celery worker."""
    from sqlalchemy import create_engine, text

    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE audit_logs SET algorand_tx_id = :tx_id WHERE id = :aid"),
            {"tx_id": tx_id, "aid": audit_log_id},
        )
        conn.commit()


def _update_policy_tx_id(policy_id: str, tx_id: str) -> None:
    """Synchronous DB update inside Celery worker."""
    from sqlalchemy import create_engine, text

    sync_url = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE policies SET algorand_tx_id = :tx_id WHERE id = :pid"),
            {"tx_id": tx_id, "pid": policy_id},
        )
        conn.commit()
