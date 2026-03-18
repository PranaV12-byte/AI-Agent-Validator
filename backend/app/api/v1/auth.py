"""Authentication endpoints for tenant signup and login."""

from datetime import datetime, timedelta, timezone
import secrets

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


def _hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_access_token(tenant_id: str) -> str:
    """Issue JWT access token for a tenant."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    payload = {
        "sub": tenant_id,
        "exp": int(expires_at.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


@router.post(
    "/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a tenant account and return JWT plus API key."""
    existing = await db.execute(select(Tenant).where(Tenant.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    api_key = secrets.token_hex(32)
    tenant = Tenant(
        company_name=body.company_name,
        email=body.email,
        password_hash=_hash_password(body.password),
        api_key=api_key,
        api_key_prefix=api_key[:8],
        active_policy_version=0,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    db.add(SafetyConfig(tenant_id=tenant.id))
    await db.commit()
    await db.refresh(tenant)

    token = _create_access_token(str(tenant.id))
    return AuthResponse(access_token=token, api_key=tenant.api_key)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate a tenant and return JWT plus API key."""
    result = await db.execute(select(Tenant).where(Tenant.email == body.email))
    tenant = result.scalar_one_or_none()
    if not tenant or not _verify_password(body.password, tenant.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not tenant.is_active:
        raise HTTPException(status_code=403, detail="Tenant account is inactive")

    token = _create_access_token(str(tenant.id))
    return AuthResponse(access_token=token, api_key=tenant.api_key)
