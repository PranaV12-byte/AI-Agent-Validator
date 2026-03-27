from collections.abc import Generator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.core.rate_limit import limiter


@pytest.fixture(scope="session")
def app() -> FastAPI:
    @asynccontextmanager
    async def noop_lifespan(_: FastAPI):
        yield

    fastapi_app.router.lifespan_context = noop_lifespan
    # Disable rate limiting for the test session so tests don't interfere
    # with each other's per-IP counters (all share 127.0.0.1).
    limiter.enabled = False
    return fastapi_app


@pytest.fixture(scope="session")
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client
