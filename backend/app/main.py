"""Safebot FastAPI Application Entry Point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1 import audit, auth, dashboard, health, hooks, policies
from app.config import settings
from app.services.guardrails import injection_detector, pii_redactor, policy_engine

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up ML models on startup, cleanup on shutdown."""
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(hooks.router, prefix="/api/v1")
app.include_router(policies.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
