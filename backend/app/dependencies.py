"""FastAPI dependency helpers for tenant authentication and DB access."""

from uuid import UUID

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
import time

from app.config import settings
from app.database import get_db
from app.models.tenant import Tenant
from app.services.api_key_cache import api_key_verify_cache
from app.services.perf_trace import emit_timing, should_trace

bearer_scheme = HTTPBearer(auto_error=False)


async def _verify_api_key(raw_api_key: str, persisted_value: str) -> bool:
    """Verify incoming API key against persisted key hash."""
    trace = should_trace()
    started = time.perf_counter() if trace else 0.0

    cached = api_key_verify_cache.get(raw_api_key, persisted_value)
    if cached is not None:
        if trace:
            emit_timing(
                "perf.api_key_verify",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                hash_mode="cache",
                valid=cached,
            )
        return cached

    if persisted_value.startswith("$2"):
        valid = await run_in_threadpool(
            bcrypt.checkpw,
            raw_api_key.encode("utf-8"),
            persisted_value.encode("utf-8"),
        )
    else:
        valid = raw_api_key == persisted_value

    api_key_verify_cache.set(raw_api_key, persisted_value, valid)

    if trace:
        emit_timing(
            "perf.api_key_verify",
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            hash_mode="bcrypt" if persisted_value.startswith("$2") else "plain",
            valid=valid,
        )

    return valid


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Resolve tenant from JWT bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        tenant_id = UUID(subject)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found or inactive",
        )
    return tenant


async def get_tenant_by_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Resolve tenant from SDK API key header."""
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if len(x_api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    key_prefix = x_api_key[:8]
    result = await db.execute(
        select(Tenant).where(
            Tenant.api_key_prefix == key_prefix,
            Tenant.is_active.is_(True),
        )
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    persisted_api_key = tenant.api_key  # type: ignore[assignment]
    is_valid = await _verify_api_key(x_api_key, persisted_api_key)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return tenant
