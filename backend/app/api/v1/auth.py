"""Authentication endpoints for tenant signup and login."""

from datetime import datetime, timedelta, timezone
import json
import secrets
from uuid import UUID
from typing import cast

import bcrypt
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis
from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegenerateApiKeyResponse,
    ResetPasswordRequest,
    SignupRequest,
    TenantProfileResponse,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["Auth"])


def _hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _generate_api_key() -> str:
    """Generate a random API key value."""
    return secrets.token_hex(32)


def _hash_api_key(api_key: str) -> str:
    """Hash API key with bcrypt before persisting."""
    return bcrypt.hashpw(api_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


_bearer_scheme = HTTPBearer(auto_error=False)
_JWT_BLOCKLIST_PREFIX = "jwt_blocklist:"
_REFRESH_TOKEN_PREFIX = "refresh_token:"
_REFRESH_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"


async def _create_refresh_token(tenant_id: str) -> tuple[str, str]:
    """Generate an opaque refresh token and persist it in Redis.

    Returns (token, family). The family ID is used to detect replay attacks:
    if a consumed token is presented again, the entire family is revoked.
    """
    token = secrets.token_urlsafe(settings.refresh_token_length)
    family = secrets.token_urlsafe(16)
    redis = await get_redis()
    ttl = settings.refresh_token_ttl_days * 86400
    await redis.setex(
        f"{_REFRESH_TOKEN_PREFIX}{token}",
        ttl,
        json.dumps({"tenant_id": tenant_id, "family": family}),
    )
    return token, family


async def _consume_refresh_token(token: str) -> tuple[str, str] | None:
    """Atomically GET+DELETE a refresh token from Redis.

    Returns (tenant_id, family) if valid, None if missing/expired.
    """
    redis = await get_redis()
    key = f"{_REFRESH_TOKEN_PREFIX}{token}"
    raw = await redis.getdel(key)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data["tenant_id"], data["family"]
    except (json.JSONDecodeError, KeyError):
        return None


async def _revoke_refresh_family(family: str) -> None:
    """Mark a refresh token family as revoked in Redis."""
    redis = await get_redis()
    ttl = settings.refresh_token_ttl_days * 86400
    await redis.setex(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{family}", ttl, "1")


async def _is_family_revoked(family: str) -> bool:
    """Check whether a refresh token family has been revoked."""
    redis = await get_redis()
    result = await redis.get(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{family}")
    return result is not None


async def _revoke_all_sessions_for_tenant(tenant_id: str) -> None:
    """Revoke all refresh tokens belonging to a tenant.

    Scans Redis for refresh tokens associated with the tenant_id,
    revokes each token's family, then deletes the token key.
    """
    redis = await get_redis()
    cursor: int | str = 0
    while True:
        cursor, keys = await redis.scan(
            cursor, match=f"{_REFRESH_TOKEN_PREFIX}*", count=100
        )
        for key in keys:
            raw = await redis.get(key)
            if raw is None:
                continue
            try:
                data = json.loads(raw)
                if data.get("tenant_id") == tenant_id:
                    family = data.get("family")
                    if family:
                        await _revoke_refresh_family(family)
                    await redis.delete(key)
            except (json.JSONDecodeError, KeyError):
                pass
        if cursor == 0:
            break


def _create_access_token(tenant_id: str) -> str:
    """Issue JWT access token for a tenant."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": tenant_id,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),  # unique token ID for revocation
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


@router.post(
    "/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a tenant account and return JWT plus API key."""
    existing = await db.execute(select(Tenant).where(Tenant.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    raw_api_key = _generate_api_key()
    tenant = Tenant(
        company_name=body.company_name,
        email=body.email,
        password_hash=_hash_password(body.password),
        api_key=_hash_api_key(raw_api_key),
        api_key_prefix=raw_api_key[:8],
        active_policy_version=0,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    db.add(SafetyConfig(tenant_id=tenant.id))
    await db.commit()
    await db.refresh(tenant)

    logger.info("auth.signup", tenant_id=str(tenant.id), email=body.email)
    token = _create_access_token(str(tenant.id))
    refresh_token, _ = await _create_refresh_token(str(tenant.id))
    return AuthResponse(access_token=token, api_key=raw_api_key, refresh_token=refresh_token)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate a tenant and return JWT plus API key."""
    result = await db.execute(select(Tenant).where(Tenant.email == body.email))
    tenant = result.scalar_one_or_none()
    if not tenant or not _verify_password(
        body.password, cast(str, tenant.password_hash)
    ):
        logger.warning("auth.login_failed", email=body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not cast(bool, tenant.is_active):
        logger.warning("auth.login_inactive", email=body.email)
        raise HTTPException(status_code=403, detail="Tenant account is inactive")

    logger.info("auth.login_success", tenant_id=str(tenant.id))
    token = _create_access_token(str(tenant.id))
    refresh_token, _ = await _create_refresh_token(str(tenant.id))
    return AuthResponse(access_token=token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    Uses single-use rotation: the presented token is consumed and a new one
    issued within the same family. If a consumed token is replayed, the family
    is revoked (stolen token detected).
    """
    result = await _consume_refresh_token(body.refresh_token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    tenant_id, family = result

    if await _is_family_revoked(family):
        logger.warning("auth.refresh_replay_detected", tenant_id=tenant_id, family=family)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    db_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = db_result.scalar_one_or_none()
    if tenant is None or not cast(bool, tenant.is_active):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Issue a new token pair within the same family
    new_access_token = _create_access_token(str(tenant.id))
    new_refresh_token = secrets.token_urlsafe(settings.refresh_token_length)
    redis = await get_redis()
    ttl = settings.refresh_token_ttl_days * 86400
    await redis.setex(
        f"{_REFRESH_TOKEN_PREFIX}{new_refresh_token}",
        ttl,
        json.dumps({"tenant_id": tenant_id, "family": family}),
    )

    logger.info("auth.token_refreshed", tenant_id=tenant_id)
    return AuthResponse(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    body: LogoutRequest | None = Body(default=None),
) -> dict:
    """Invalidate the current JWT and optionally revoke the refresh token.

    Always returns 200 — clients should clear their local session regardless.
    """
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                ttl = max(1, exp - int(datetime.now(timezone.utc).timestamp()))
                redis = await get_redis()
                await redis.setex(f"{_JWT_BLOCKLIST_PREFIX}{jti}", ttl, "1")
        except (JWTError, ValueError):
            pass  # Token already invalid — no blocklist entry needed

    if body and body.refresh_token:
        result = await _consume_refresh_token(body.refresh_token)
        if result:
            _, family = result
            await _revoke_refresh_family(family)

    return {"message": "Logged out."}


@router.get("/me", response_model=TenantProfileResponse)
async def get_me(tenant: Tenant = Depends(get_current_tenant)) -> TenantProfileResponse:
    """Return current tenant profile for authenticated session."""
    return TenantProfileResponse(
        id=cast(UUID, tenant.id),
        company_name=cast(str, tenant.company_name),
        email=cast(str, tenant.email),
        api_key_prefix=cast(str, tenant.api_key_prefix),
        active_policy_version=cast(int, tenant.active_policy_version),
    )


@router.post("/regenerate-key", response_model=RegenerateApiKeyResponse)
async def regenerate_key(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> RegenerateApiKeyResponse:
    """Rotate tenant API key and return the one-time raw value."""
    raw_api_key = _generate_api_key()
    tenant.api_key = _hash_api_key(raw_api_key)
    tenant.api_key_prefix = raw_api_key[:8]

    await db.flush()
    await db.commit()

    logger.info("auth.api_key_regenerated", tenant_id=str(tenant.id), new_prefix=raw_api_key[:8])
    return RegenerateApiKeyResponse(
        api_key=raw_api_key,
        api_key_prefix=cast(str, tenant.api_key_prefix),
    )


_RESET_KEY_PREFIX = "password_reset:"


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """Initiate password reset — generates a token stored in Redis.

    Always returns HTTP 200 regardless of whether the email is registered,
    to avoid leaking account existence.  In development the reset URL is
    also returned in the response body so the developer can act on it
    without an email server.
    """
    result = await db.execute(select(Tenant).where(Tenant.email == body.email))
    tenant = result.scalar_one_or_none()

    generic_message = (
        "If that email is registered you will receive a password-reset link shortly."
    )

    if tenant is None:
        return ForgotPasswordResponse(message=generic_message)

    token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.setex(
        f"{_RESET_KEY_PREFIX}{token}",
        settings.password_reset_token_ttl_seconds,
        str(tenant.id),
    )

    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    logger.info("password_reset_requested", email=body.email, reset_url=reset_url)

    reset_url_in_response = reset_url if settings.environment in ("development", "test") else None
    return ForgotPasswordResponse(message=generic_message, reset_url=reset_url_in_response)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Consume a password-reset token and update the tenant's password."""
    redis = await get_redis()
    redis_key = f"{_RESET_KEY_PREFIX}{body.token}"
    tenant_id = await redis.get(redis_key)

    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None or not cast(bool, tenant.is_active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # Consume token immediately (single-use).
    await redis.delete(redis_key)

    tenant.password_hash = _hash_password(body.new_password)
    await db.commit()

    # Revoke all existing refresh token families so stolen tokens cannot
    # be exchanged for new access tokens after the password changes.
    await _revoke_all_sessions_for_tenant(str(tenant_id))

    logger.info("password_reset_completed", tenant_id=tenant_id)
    return {"message": "Password updated successfully."}
