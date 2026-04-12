"""
Async SQLAlchemy engine, session factory, and ORM Base.

Engine is created once at module load using settings from config.py.
All routes obtain a DB session via the `get_db` async generator,
which commits on success and rolls back on any exception.
"""

from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import ssl as _ssl_module

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _build_engine_args(url: str) -> tuple[str, dict]:
    """Extract ssl param from URL and return (clean_url, connect_args).

    asyncpg does not recognise ?ssl=disable as a URL query parameter —
    it must be passed via connect_args.  This helper strips the ``ssl``
    query parameter from the URL and converts it into the correct
    ``connect_args`` dict for asyncpg.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    connect_args: dict = {}

    ssl_values = qs.pop("ssl", None)
    if ssl_values:
        val = ssl_values[0].lower()
        if val in ("disable", "false", "0", "no"):
            connect_args["ssl"] = False
        elif val in ("require", "true", "1", "yes"):
            ctx = _ssl_module.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl_module.CERT_NONE
            connect_args["ssl"] = ctx

    # Rebuild URL without the ssl query param
    new_query = urlencode(qs, doseq=True)
    clean_url = urlunparse(parsed._replace(query=new_query))
    return clean_url, connect_args


_clean_url, _connect_args = _build_engine_args(settings.database_url)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    _clean_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    echo=settings.debug,
    connect_args=_connect_args,
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All SQLAlchemy models inherit from this Base."""


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async DB session.

    Commits on clean exit; rolls back on any exception; always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
