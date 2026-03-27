"""Health check endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.redis_client import get_redis
from app.database import AsyncSessionLocal
from app.services.guardrails import injection_detector, pii_redactor, policy_engine

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """Deep readiness check — verifies DB, Redis, and ML model readiness.

    Returns HTTP 200 when all dependencies are reachable, 503 otherwise.
    Load balancers should route traffic based on this endpoint.
    """
    checks: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "error"

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    checks["model_injection"] = "ok" if injection_detector.is_ready else "not_loaded"
    checks["model_pii"] = "ok" if pii_redactor.is_ready else "not_loaded"
    checks["model_policy"] = "ok" if policy_engine.is_ready else "not_loaded"

    all_ok = all(v == "ok" for v in checks.values())
    body = {"status": "healthy" if all_ok else "degraded", "checks": checks}
    return JSONResponse(content=body, status_code=200 if all_ok else 503)


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Lightweight liveness probe — no external dependencies checked."""
    return {"status": "ok"}
