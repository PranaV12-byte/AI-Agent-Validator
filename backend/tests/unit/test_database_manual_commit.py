"""The protected-chat DB dependency has bounded explicit cleanup."""

import asyncio

import pytest
from starlette.requests import Request

from app import database


@pytest.mark.asyncio
async def test_manual_commit_path_bounds_rollback_and_close(monkeypatch) -> None:
    class HangingSession:
        committed = False
        rollback_started = False
        close_started = False

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rollback_started = True
            await asyncio.Event().wait()

        async def close(self) -> None:
            self.close_started = True
            await asyncio.Event().wait()

    session = HangingSession()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(database, "MANUAL_SESSION_CLEANUP_TIMEOUT_SECONDS", 0.01)
    request = Request({"type": "http", "headers": []})
    setattr(request.state, database.MANUAL_COMMIT_REQUEST_STATE_KEY, True)
    dependency = database.get_db(request)

    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(dependency), timeout=0.2)

    assert session.rollback_started is True
    assert session.close_started is True
    assert session.committed is False
