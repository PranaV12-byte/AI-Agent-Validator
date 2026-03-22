"""Simple database connectivity check for perf preflight."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check DB connectivity")
    parser.add_argument("--output-body", required=True)
    parser.add_argument("--output-status", required=True)
    return parser.parse_args()


async def _run() -> tuple[int, dict[str, object]]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return 200, {"status": "ok"}
    except Exception as exc:  # pragma: no cover - diagnostic path
        return 500, {"status": "error", "detail": str(exc)}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    args = _parse_args()
    code, payload = asyncio.run(_run())

    with open(args.output_status, "w", encoding="utf-8") as status_file:
        status_file.write(str(code))

    with open(args.output_body, "w", encoding="utf-8") as body_file:
        json.dump(payload, body_file)
