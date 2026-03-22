"""Lightweight performance tracing helpers."""

from __future__ import annotations

import random
from collections.abc import Callable

import structlog

from app.config import settings

logger = structlog.get_logger()


def should_trace() -> bool:
    """Decide if current request should emit performance telemetry."""
    if not settings.perf_trace_enabled:
        return False
    return random.random() <= max(0.0, min(1.0, settings.perf_trace_sample_rate))


def emit_timing(event: str, **fields: object) -> None:
    """Emit a structured timing event."""
    logger.info(event, **fields)


def timed_block_ms(fn: Callable[[], object]) -> tuple[object, int]:
    """Execute sync callable and return result with elapsed ms."""
    import time

    started = time.perf_counter()
    result = fn()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result, elapsed_ms
