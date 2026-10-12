"""Pure unit coverage for the integration-suite mutation safety gate."""

import pytest

from tests.safety_guard import UnsafeTestEnvironment, validate_test_environment


def _env() -> dict[str, str]:
    return {
        "SAFEBOT_ALLOW_TEST_MUTATIONS": "1",
        "SAFEBOT_TEST_DATABASE_NAME": "safebot_test",
        "SAFEBOT_TEST_REDIS_URL": "redis://127.0.0.1:16379/0",
    }


def test_test_environment_guard_accepts_exact_disposable_targets() -> None:
    validate_test_environment(
        environment="test",
        database_url="postgresql+asyncpg://user:pass@127.0.0.1:55432/safebot_test",
        redis_url="redis://127.0.0.1:16379/0",
        env=_env(),
    )


@pytest.mark.parametrize(
    ("environment", "database_url", "redis_url", "env"),
    [
        ("development", "postgresql+asyncpg://localhost/db_test", "redis://localhost:16379/0", _env()),
        ("test", "postgresql+asyncpg://localhost/safebot", "redis://localhost:16379/0", _env()),
        ("test", "postgresql+asyncpg://localhost/safebot_test", "redis://localhost:6379/0", _env()),
        ("test", "postgresql+asyncpg://localhost/safebot_test", "redis://localhost:16379/0", {**_env(), "SAFEBOT_ALLOW_TEST_MUTATIONS": "0"}),
    ],
)
def test_test_environment_guard_rejects_unapproved_targets(
    environment: str,
    database_url: str,
    redis_url: str,
    env: dict[str, str],
) -> None:
    with pytest.raises(UnsafeTestEnvironment):
        validate_test_environment(
            environment=environment,
            database_url=database_url,
            redis_url=redis_url,
            env=env,
        )
