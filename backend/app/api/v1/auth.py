"""Authentication endpoints for tenant signup and login."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from uuid import UUID
from typing import cast

import bcrypt
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.config import settings
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis
from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegenerateApiKeyResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    TenantProfileResponse,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from app.services.email_service import send_password_reset_email, send_verification_email

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


async def _increment_auth_version(db: AsyncSession, tenant: Tenant) -> int:
    """Atomically advance the persisted version so concurrent mutations cannot lose an increment."""
    result = await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant.id)
        .values(auth_version=Tenant.auth_version + 1)
        .returning(Tenant.auth_version)
        .execution_options(synchronize_session=False)
    )
    auth_version = result.scalar_one_or_none()
    if auth_version is None:
        raise HTTPException(status_code=401, detail="Tenant not found or inactive")
    version = int(auth_version)
    set_committed_value(tenant, "auth_version", version)
    return version


_bearer_scheme = HTTPBearer(auto_error=False)
_JWT_BLOCKLIST_PREFIX = "jwt_blocklist:"
_REFRESH_TOKEN_PREFIX = "refresh_token:"
_REFRESH_TOKEN_CONSUMED_PREFIX = "refresh_token_consumed:"
_REFRESH_FAMILY_REVOKED_PREFIX = "refresh_family_revoked:"


_CONSUME_REFRESH_TOKEN_SCRIPT = """
local active = redis.call("GET", KEYS[1])
if active then
    redis.call("DEL", KEYS[1])
    redis.call("SET", KEYS[2], active, "EX", ARGV[1])
    return {1, active}
end
local consumed = redis.call("GET", KEYS[2])
if consumed then
    local decoded, metadata = pcall(cjson.decode, consumed)
    if decoded and type(metadata) == "table" and metadata["family"] then
        redis.call("SET", ARGV[2] .. metadata["family"], "1", "EX", ARGV[1])
    end
    return {2, consumed}
end
return {0, ""}
"""


async def _store_refresh_token(
    token: str,
    tenant_id: str,
    family: str,
    auth_version: int,
) -> None:
    redis = await get_redis()
    ttl = max(1, settings.refresh_token_ttl_days * 86400)
    await redis.setex(
        f"{_REFRESH_TOKEN_PREFIX}{token}",
        ttl,
        json.dumps(
            {
                "tenant_id": tenant_id,
                "family": family,
                "auth_version": auth_version,
            }
        ),
    )


async def _create_refresh_token(
    tenant_id: str,
    auth_version: int = 0,
) -> tuple[str, str]:
    """Generate an opaque refresh token and persist it in Redis.

    Returns (token, family). The family ID is used to detect replay attacks:
    if a consumed token is presented again, the entire family is revoked.
    """
    token = secrets.token_urlsafe(settings.refresh_token_length)
    family = secrets.token_urlsafe(16)
    await _store_refresh_token(token, tenant_id, family, auth_version)
    return token, family


async def _consume_refresh_token(token: str) -> tuple[str, str, int] | None:
    """Consume a refresh token once and retain a hashed replay marker.

    The Lua script makes consuming the token and recording its family metadata
    one Redis operation. Replaying a consumed token revokes its whole family.
    """
    redis = await get_redis()
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    active_key = f"{_REFRESH_TOKEN_PREFIX}{token}"
    consumed_key = f"{_REFRESH_TOKEN_CONSUMED_PREFIX}{token_digest}"
    ttl = max(1, settings.refresh_token_ttl_days * 86400)
    result = await redis.eval(
        _CONSUME_REFRESH_TOKEN_SCRIPT,
        2,
        active_key,
        consumed_key,
        ttl,
        _REFRESH_FAMILY_REVOKED_PREFIX,
    )
    if not result:
        return None

    try:
        result_status = int(result[0])
        raw = result[1]
        if result_status == 0 or raw in (None, ""):
            return None
        data = json.loads(raw)
        tenant_id = data["tenant_id"]
        family = data["family"]
        auth_version = data.get("auth_version", 0)
        if (
            result_status not in (1, 2)
            or not isinstance(tenant_id, str)
            or not isinstance(family, str)
            or not family
            or isinstance(auth_version, bool)
            or not isinstance(auth_version, int)
            or auth_version < 0
        ):
            return None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None

    if result_status == 2:
        logger.warning("auth.refresh_replay_detected", tenant_id=tenant_id)
        return None

    return tenant_id, family, auth_version


async def _create_email_verification_url(tenant: Tenant) -> str:
    verify_token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.setex(
        f"{_EMAIL_VERIFY_PREFIX}{verify_token}",
        settings.email_verification_token_ttl_seconds,
        json.dumps(
            {
                "tenant_id": str(tenant.id),
                "auth_version": int(tenant.auth_version or 0),
            }
        ),
    )
    return f"{settings.frontend_url}/verify-email?token={verify_token}"


async def _revoke_refresh_family(family: str) -> None:
    """Mark a refresh token family as revoked in Redis."""
    redis = await get_redis()
    ttl = max(1, settings.refresh_token_ttl_days * 86400)
    await redis.setex(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{family}", ttl, "1")


async def _is_family_revoked(family: str) -> bool:
    """Check whether a refresh token family has been revoked."""
    redis = await get_redis()
    result = await redis.get(f"{_REFRESH_FAMILY_REVOKED_PREFIX}{family}")
    return result is not None


def _create_access_token(
    tenant_id: str,
    auth_version: int = 0,
    session_family: str | None = None,
) -> str:
    """Issue JWT access token for a tenant."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": tenant_id,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16),  # unique token ID for revocation
        "auth_version": auth_version,
    }
    if session_family is not None:
        payload["session_family"] = session_family
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

    # In development and test environments, auto-verify email so the developer
    # can sign in immediately without needing an SMTP server.
    auto_verified = settings.environment in ("development", "test")

    raw_api_key = _generate_api_key()
    tenant = Tenant(
        company_name=body.company_name,
        email=body.email,
        password_hash=_hash_password(body.password),
        api_key=_hash_api_key(raw_api_key),
        api_key_prefix=raw_api_key[:8],
        active_policy_version=0,
        is_active=True,
        email_verified=auto_verified,
    )
    db.add(tenant)
    await db.flush()

    db.add(SafetyConfig(tenant_id=tenant.id))
    await db.commit()
    await db.refresh(tenant)

    logger.info("auth.signup", tenant_id=str(tenant.id), email=body.email, email_verified=auto_verified)

    verification_url_in_response: str | None = None
    if not auto_verified:
        verify_url = await _create_email_verification_url(tenant)
        logger.info("email_verification_token_created", tenant_id=str(tenant.id))
        await send_verification_email(body.email, verify_url)
        # Never expose the token URL in production responses
        verification_url_in_response = None
    else:
        # Expose in dev/test so devs can skip the email step
        verify_url = await _create_email_verification_url(tenant)
        logger.info("email_verification_token_created", tenant_id=str(tenant.id))
        verification_url_in_response = verify_url

    auth_version = int(tenant.auth_version or 0)
    refresh_token, family = await _create_refresh_token(str(tenant.id), auth_version)
    token = _create_access_token(str(tenant.id), auth_version, family)
    return AuthResponse(
        access_token=token,
        api_key=raw_api_key,
        refresh_token=refresh_token,
        email_verified=auto_verified,
        verification_url=verification_url_in_response,
    )


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

    if not cast(bool, tenant.email_verified):
        logger.warning("auth.login_unverified_email", email=body.email)
        raise HTTPException(
            status_code=403,
            detail="Email address not verified. Please check your inbox or request a new verification link.",
        )

    logger.info("auth.login_success", tenant_id=str(tenant.id))
    auth_version = int(tenant.auth_version or 0)
    refresh_token, family = await _create_refresh_token(str(tenant.id), auth_version)
    token = _create_access_token(str(tenant.id), auth_version, family)
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

    tenant_id, family, token_auth_version = result

    if await _is_family_revoked(family):
        logger.warning("auth.refresh_replay_detected", tenant_id=tenant_id)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    db_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = db_result.scalar_one_or_none()
    if (
        tenant is None
        or not cast(bool, tenant.is_active)
        or token_auth_version != int(tenant.auth_version or 0)
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Issue a new token pair within the same family
    new_access_token = _create_access_token(
        str(tenant.id), int(tenant.auth_version or 0), family
    )
    new_refresh_token = secrets.token_urlsafe(settings.refresh_token_length)
    await _store_refresh_token(
        new_refresh_token, tenant_id, family, int(tenant.auth_version or 0)
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
            _, family, _ = result
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


@router.put("/me", response_model=TenantProfileResponse)
@limiter.limit("5/hour")
async def update_me(
    request: Request,
    body: UpdateProfileRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantProfileResponse:
    """Update current tenant's company name or email."""
    verification_url: str | None = None
    if body.company_name is not None:
        tenant.company_name = body.company_name

    if body.email is not None and body.email != cast(str, tenant.email):
        existing = await db.execute(
            select(Tenant).where(
                Tenant.email == body.email,
                Tenant.id != tenant.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered.")
        tenant.email = body.email
        tenant.email_verified = False
        await _increment_auth_version(db, tenant)
        verify_url = await _create_email_verification_url(tenant)
        logger.info("email_verification_token_created", tenant_id=str(tenant.id))
        if settings.environment not in ("development", "test"):
            await send_verification_email(body.email, verify_url)
        else:
            verification_url = verify_url

    await db.commit()
    await db.refresh(tenant)
    logger.info("auth.profile_updated", tenant_id=str(tenant.id))
    return TenantProfileResponse(
        id=cast(UUID, tenant.id),
        company_name=cast(str, tenant.company_name),
        email=cast(str, tenant.email),
        api_key_prefix=cast(str, tenant.api_key_prefix),
        active_policy_version=cast(int, tenant.active_policy_version),
        verification_url=verification_url,
    )


@router.post("/regenerate-key", response_model=RegenerateApiKeyResponse)
@limiter.limit("3/hour")
async def regenerate_key(
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> RegenerateApiKeyResponse:
    """Rotate tenant API key and return the one-time raw value."""
    raw_api_key = _generate_api_key()
    tenant.api_key = _hash_api_key(raw_api_key)
    tenant.api_key_prefix = raw_api_key[:8]

    await db.flush()
    await db.commit()

    logger.info("auth.api_key_regenerated", tenant_id=str(tenant.id))
    return RegenerateApiKeyResponse(
        api_key=raw_api_key,
        api_key_prefix=cast(str, tenant.api_key_prefix),
    )


_RESET_KEY_PREFIX = "password_reset:"
_EMAIL_VERIFY_PREFIX = "email_verification:"


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
    logger.info("password_reset_requested", tenant_id=str(tenant.id))

    # Always attempt to send the email — send_password_reset_email is a no-op
    # when SMTP is not configured (logs a warning instead).
    await send_password_reset_email(body.email, reset_url)

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
    # Atomic GET+DELETE — prevents replay even under concurrent requests
    tenant_id = await redis.getdel(redis_key)

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

    tenant.password_hash = _hash_password(body.new_password)
    await _increment_auth_version(db, tenant)
    await db.commit()

    logger.info("password_reset_completed", tenant_id=tenant_id)
    return {"message": "Password updated successfully."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Consume an email verification token and mark the tenant's email as verified."""
    redis = await get_redis()
    raw_verification = await redis.getdel(f"{_EMAIL_VERIFY_PREFIX}{body.token}")

    if raw_verification is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )

    try:
        verification_data = json.loads(raw_verification)
        if isinstance(verification_data, dict):
            tenant_id = verification_data["tenant_id"]
            token_auth_version = verification_data.get("auth_version", 0)
        else:
            tenant_id = raw_verification
            token_auth_version = 0
    except (json.JSONDecodeError, KeyError, TypeError):
        # Legacy links stored only the tenant ID and remain valid until their
        # existing TTL, unless the account has since changed its email.
        tenant_id = raw_verification
        token_auth_version = 0

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if (
        tenant is None
        or not cast(bool, tenant.is_active)
        or isinstance(token_auth_version, bool)
        or not isinstance(token_auth_version, int)
        or token_auth_version != int(tenant.auth_version or 0)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )

    if cast(bool, tenant.email_verified):
        # Already verified — idempotent success
        return {"message": "Email already verified."}

    tenant.email_verified = True
    await db.commit()

    logger.info("email_verified", tenant_id=tenant_id)
    return {"message": "Email verified successfully. You can now sign in."}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-send the email verification link.

    Always returns 200 regardless of whether the email is registered or already
    verified, to prevent account enumeration.
    """
    generic_message = "If that email is registered and unverified, a new link has been sent."

    result = await db.execute(select(Tenant).where(Tenant.email == body.email))
    tenant = result.scalar_one_or_none()

    if tenant is None or cast(bool, tenant.email_verified):
        return {"message": generic_message}

    verify_url = await _create_email_verification_url(tenant)
    logger.info("email_verification_resent", tenant_id=str(tenant.id))
    await send_verification_email(body.email, verify_url)

    response = {"message": generic_message}
    if settings.environment in ("development", "test"):
        response["verification_url"] = verify_url
    return response


@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the current tenant's password (requires existing valid password)."""
    if not _verify_password(body.current_password, cast(str, tenant.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    tenant.password_hash = _hash_password(body.new_password)
    await _increment_auth_version(db, tenant)
    await db.commit()
    logger.info("auth.password_changed", tenant_id=str(tenant.id))
    return {"message": "Password updated successfully."}
