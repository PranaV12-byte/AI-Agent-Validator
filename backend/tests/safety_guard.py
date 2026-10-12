"""Explicit opt-in guard for tests that mutate PostgreSQL or Redis."""

from __future__ import annotations

import os
import re

from sqlalchemy.engine import make_url


_TEST_DATABASE_NAME = re.compile(r"(?:^test_|_test$)", re.IGNORECASE)


class UnsafeTestEnvironment(RuntimeError):
    """Raised when the configured services are not explicitly test-only."""


def validate_test_environment(
    *,
    environment: str,
    database_url: str,
    redis_url: str,
    env: dict[str, str] | None = None,
) -> None:
    """Require explicit names for the disposable database and Redis service.

    Error text deliberately omits connection strings because they can contain
    credentials. Tests create accounts, policies, audit rows, and Redis tokens.
    """
    values = os.environ if env is None else env

    if environment.casefold() != "test":
        raise UnsafeTestEnvironment("ENVIRONMENT must be 'test' before running tests.")

    if values.get("SAFEBOT_ALLOW_TEST_MUTATIONS") != "1":
        raise UnsafeTestEnvironment(
            "Set SAFEBOT_ALLOW_TEST_MUTATIONS=1 only for a disposable test stack."
        )

    expected_database = values.get("SAFEBOT_TEST_DATABASE_NAME", "")
    try:
        actual_database = make_url(database_url).database or ""
    except Exception as exc:
        raise UnsafeTestEnvironment("DATABASE_URL is not a valid database URL.") from exc

    if (
        not _TEST_DATABASE_NAME.search(expected_database)
        or actual_database != expected_database
    ):
        raise UnsafeTestEnvironment(
            "DATABASE_URL must target the exact SAFEBOT_TEST_DATABASE_NAME, "
            "which must start with 'test_' or end with '_test'."
        )

    expected_redis_url = values.get("SAFEBOT_TEST_REDIS_URL", "")
    if not expected_redis_url or redis_url != expected_redis_url:
        raise UnsafeTestEnvironment(
            "REDIS_URL must exactly match the separately configured "
            "SAFEBOT_TEST_REDIS_URL."
        )
