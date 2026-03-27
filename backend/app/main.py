"""Safebot FastAPI Application Entry Point."""

from contextlib import asynccontextmanager

import logging

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded

from app.api.v1 import audit, auth, dashboard, health, hooks, policies
from app.config import settings
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.services.guardrails import injection_detector, pii_redactor, policy_engine

# 5.5 — Configure structlog: JSON in production, human-readable in development.
_PII_FIELDS = frozenset({"email", "password", "api_key", "token", "mnemonic", "reset_url"})


def _mask_pii(logger, method, event_dict):  # noqa: ARG001
    """Drop known PII fields from every log record."""
    for field in _PII_FIELDS:
        if field in event_dict:
            event_dict[field] = "***"
    return event_dict


_shared_processors = [
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    _mask_pii,
]

if settings.environment == "production":
    structlog.configure(
        processors=[
            *_shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
else:
    structlog.configure(
        processors=[
            *_shared_processors,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

logger = structlog.get_logger()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    logger.info("sentry_initialized", environment=settings.environment)
elif settings.environment not in ("development", "test"):
    logger.warning(
        "sentry_not_configured",
        msg="SENTRY_DSN is not set — unhandled errors will NOT be tracked. "
            "Set SENTRY_DSN to enable error monitoring.",
    )


_INSECURE_JWT_SECRETS = {"", "CHANGE-ME", "CHANGE_ME", "secret", "changeme", "your-secret-key"}
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up ML models on startup, cleanup on shutdown."""
    # Reject unsafe JWT algorithm choices
    if settings.jwt_algorithm not in _ALLOWED_JWT_ALGORITHMS:
        raise RuntimeError(
            f"JWT_ALGORITHM '{settings.jwt_algorithm}' is not allowed. "
            f"Must be one of: {', '.join(sorted(_ALLOWED_JWT_ALGORITHMS))}"
        )

    # Refuse to start with a weak JWT secret outside development
    if settings.environment != "development":
        secret = settings.jwt_secret_key.strip()
        if not secret or secret in _INSECURE_JWT_SECRETS or len(secret) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be a secure random value (≥32 chars) in non-development "
                "environments. Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    if settings.environment == "production":
        # 3.1 — Reject localhost CORS origins and frontend URL in production
        localhost_markers = ("localhost", "127.0.0.1", "0.0.0.0")
        bad_origins = [o for o in settings.cors_origins if any(m in o for m in localhost_markers)]
        if bad_origins:
            raise RuntimeError(
                f"CORS_ORIGINS contains localhost entries in production: {bad_origins}. "
                "Set CORS_ORIGINS to your real domain(s)."
            )
        if any(m in settings.frontend_url for m in localhost_markers):
            raise RuntimeError(
                f"FRONTEND_URL is set to '{settings.frontend_url}' in production. "
                "Set FRONTEND_URL to your real domain."
            )
        # 3.5 — Block debug mode in production
        if settings.debug:
            raise RuntimeError(
                "DEBUG=true is not allowed in production — SQL queries and stack traces "
                "would be exposed. Set DEBUG=false."
            )

    if settings.algorand_app_id == 0:
        logger.warning(
            "algorand_mock_mode",
            msg="algorand_app_id=0: all blockchain writes return MOCK TX IDs. "
                "Audit logs are NOT immutably recorded on-chain. "
                "Set ALGORAND_APP_ID to enable real blockchain writes.",
        )
        if settings.environment == "production":
            raise RuntimeError(
                "ALGORAND_APP_ID must be set in production. "
                "Mock TX IDs are not acceptable for production compliance audit trails."
            )

    logger.info("startup", msg="Loading ML models...")
    injection_detector.load_model()
    pii_redactor.load_model()
    policy_engine.load_model()
    logger.info("startup_complete", msg="All models loaded. Safebot ready.")
    yield
    logger.info("shutdown", msg="Safebot shutting down gracefully.")


app = FastAPI(
    title="Safebot API",
    description="AI Guardrails Middleware for SMBs",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Attach security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.environment != "development":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(hooks.router, prefix="/api/v1")
app.include_router(hooks.validate_router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
