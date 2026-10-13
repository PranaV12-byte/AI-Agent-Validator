from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.dashboard import get_dashboard_stats


class SnapshotResult:
    def __init__(self, row):
        self._row = row

    def all(self):
        return [self._row]

    def one(self):
        return self._row


class ReadCommittedInterleavingSession:
    """Model a committed write between two READ COMMITTED SELECT statements."""

    def __init__(self, today):
        self.today = today
        self.execute_calls = 0
        self.late_write_committed = False

    def _row(self, requests, allowed, latency):
        return SimpleNamespace(
            date=self.today,
            total_requests=requests,
            allowed_requests=allowed,
            redacted_requests=0,
            blocked_requests=0,
            error_requests=0,
            total_latency_ms=latency,
            latency_conversation_count=1,
            avg_latency_ms=latency / requests,
        )

    async def execute(self, _statement):
        self.execute_calls += 1
        if self.execute_calls == 1:
            # The first SELECT has already captured its snapshot. A concurrent
            # request completes before the endpoint formats the response.
            result = SnapshotResult(self._row(requests=1, allowed=1, latency=10))
            self.late_write_committed = True
            return result
        return SnapshotResult(self._row(requests=2, allowed=2, latency=30))


@pytest.mark.asyncio
async def test_dashboard_totals_and_daily_trend_share_one_read_snapshot():
    today = datetime.now(timezone.utc).date()
    db = ReadCommittedInterleavingSession(today)

    response = await get_dashboard_stats(
        tenant=SimpleNamespace(id=uuid4()),
        db=db,
    )

    assert db.late_write_committed is True
    assert db.execute_calls == 1
    assert response.total_requests == 1
    assert response.allowed_requests == 1
    assert sum(day.allowed_requests for day in response.daily_trend) == 1
    assert response.daily_trend[-1].date == today


@pytest.mark.asyncio
async def test_dashboard_average_uses_only_conversations_with_latency():
    today = datetime.now(timezone.utc).date()
    row = SimpleNamespace(
        date=today,
        total_requests=2,
        allowed_requests=2,
        redacted_requests=0,
        blocked_requests=0,
        error_requests=0,
        total_latency_ms=100,
        latency_conversation_count=1,
    )

    class StaticSession:
        async def execute(self, _statement):
            return SnapshotResult(row)

    response = await get_dashboard_stats(
        tenant=SimpleNamespace(id=uuid4()),
        db=StaticSession(),
    )

    assert response.total_requests == 2
    assert response.avg_latency_ms == 100.0
