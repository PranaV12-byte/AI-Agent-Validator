"""
Alembic environment configuration for Safebot.

Supports async SQLAlchemy (asyncpg driver). DATABASE_URL is loaded from
app.config.settings so alembic and the application always use the same
connection string — never hard-coded here.

Usage:
    cd backend
    alembic revision --autogenerate -m "describe change"
    alembic upgrade head
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Alembic Config ─────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── App settings: override alembic.ini URL with real value from .env ───────────
from app.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.database_url)

# ── Model metadata: import Base + all models so autogenerate sees every table ──
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402  — side-effect: registers all models with Base

target_metadata = Base.metadata


# ── Offline migration ──────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates raw SQL without requiring a live DB connection.
    Useful for reviewing what will be applied before running.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migration ───────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    """Execute pending migrations on an active connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create a temporary async engine and run pending migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (live DB) migrations."""
    asyncio.run(run_async_migrations())


# ── Dispatch ───────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
