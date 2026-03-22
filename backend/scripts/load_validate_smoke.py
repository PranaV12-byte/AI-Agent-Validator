"""Load/soak validation script for /api/v1/validate.

Examples (PowerShell):
  # Smoke run
  $env:API_BASE_URL="http://localhost:8000/api/v1"
  $env:API_KEY="sk-..."
  python scripts/load_validate_smoke.py --mode smoke --total-requests 300 --concurrency 15

  # 30-minute soak run
  python scripts/load_validate_smoke.py --mode soak --duration-seconds 1800 --batch-size 30 --concurrency 10 --pause-seconds 1
"""

from __future__ import annotations

import asyncio
import argparse
import json
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass

import httpx


@dataclass
class RequestResult:
    status: int
    latency_ms: float


@dataclass
class RunSummary:
    elapsed_seconds: float
    total_requests: int
    status_counts: Counter[int]
    p50_ms: float
    p95_ms: float
    mean_ms: float
    status_latency_ms: dict[int, dict[str, float]]


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(
        0,
        min(len(sorted_values) - 1, int(round((pct / 100) * (len(sorted_values) - 1)))),
    )
    return sorted_values[index]


async def _run_once(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    prompt: str,
    sequence: int,
) -> RequestResult:
    start = time.perf_counter()
    response = await client.post(
        url,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
            "user_id": f"load-smoke-{sequence}",
        },
    )
    latency_ms = (time.perf_counter() - start) * 1000
    return RequestResult(status=response.status_code, latency_ms=latency_ms)


def _build_summary(results: list[RequestResult], elapsed_seconds: float) -> RunSummary:
    status_counts = Counter(item.status for item in results)
    latencies = sorted(item.latency_ms for item in results)
    grouped_latencies: dict[int, list[float]] = {}
    for item in results:
        grouped_latencies.setdefault(item.status, []).append(item.latency_ms)

    status_latency_ms: dict[int, dict[str, float]] = {}
    for status, values in grouped_latencies.items():
        ordered = sorted(values)
        status_latency_ms[status] = {
            "p50": _percentile(ordered, 50),
            "p95": _percentile(ordered, 95),
            "mean": statistics.mean(ordered),
        }

    return RunSummary(
        elapsed_seconds=elapsed_seconds,
        total_requests=len(results),
        status_counts=status_counts,
        p50_ms=_percentile(latencies, 50),
        p95_ms=_percentile(latencies, 95),
        mean_ms=statistics.mean(latencies) if latencies else 0.0,
        status_latency_ms=status_latency_ms,
    )


def _print_summary(summary: RunSummary, url: str, mode: str, concurrency: int) -> None:
    success = summary.status_counts.get(200, 0)
    throttled = summary.status_counts.get(429, 0)
    unauthorized = summary.status_counts.get(401, 0)
    server_errors = sum(
        count for status, count in summary.status_counts.items() if status >= 500
    )

    print("=== Validate Load Report ===")
    print(f"Mode: {mode}")
    print(f"Endpoint: {url}")
    print(f"Total requests: {summary.total_requests}")
    print(f"Concurrency: {concurrency}")
    print(f"Elapsed: {summary.elapsed_seconds:.2f}s")
    throughput = (
        summary.total_requests / summary.elapsed_seconds
        if summary.elapsed_seconds
        else 0.0
    )
    print(f"Throughput: {throughput:.2f} req/s")
    print("Status counts:", dict(sorted(summary.status_counts.items())))
    print(f"200 OK: {success}")
    print(f"429 Too Many Requests: {throttled}")
    print(f"401 Unauthorized: {unauthorized}")
    print(f"5xx Server Errors: {server_errors}")
    print(f"Latency p50: {summary.p50_ms:.2f}ms")
    print(f"Latency p95: {summary.p95_ms:.2f}ms")
    print(f"Latency mean: {summary.mean_ms:.2f}ms")
    print("Latency by status:")
    for status in sorted(summary.status_latency_ms):
        metrics = summary.status_latency_ms[status]
        print(
            f"  {status}: p50={metrics['p50']:.2f}ms p95={metrics['p95']:.2f}ms mean={metrics['mean']:.2f}ms"
        )


def _validate_thresholds(
    summary: RunSummary,
    *,
    max_server_errors: int,
    max_p95_ms: float,
    max_ok_p95_ms: float,
) -> tuple[bool, list[str]]:
    failures: list[str] = []

    server_errors = sum(
        count for status, count in summary.status_counts.items() if status >= 500
    )
    if server_errors > max_server_errors:
        failures.append(
            f"5xx errors {server_errors} exceeded threshold {max_server_errors}"
        )

    if summary.p95_ms > max_p95_ms:
        failures.append(
            f"p95 latency {summary.p95_ms:.2f}ms exceeded threshold {max_p95_ms:.2f}ms"
        )

    ok_metrics = summary.status_latency_ms.get(200)
    if ok_metrics and ok_metrics["p95"] > max_ok_p95_ms:
        failures.append(
            f"200-only p95 latency {ok_metrics['p95']:.2f}ms exceeded threshold {max_ok_p95_ms:.2f}ms"
        )

    return (len(failures) == 0, failures)


async def _run_smoke(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    prompt: str,
    total_requests: int,
    concurrency: int,
) -> RunSummary:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[RequestResult] = []

    async def worker(index: int) -> None:
        async with semaphore:
            result = await _run_once(client, url, api_key, prompt, index)
            results.append(result)

    started = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(total_requests)))
    elapsed = time.perf_counter() - started
    return _build_summary(results, elapsed)


async def _run_soak(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    prompt: str,
    duration_seconds: int,
    batch_size: int,
    concurrency: int,
    pause_seconds: float,
    report_every_batches: int,
) -> RunSummary:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[RequestResult] = []
    started = time.perf_counter()
    batch_index = 0

    while (time.perf_counter() - started) < duration_seconds:
        batch_index += 1

        async def worker(index: int) -> None:
            async with semaphore:
                result = await _run_once(
                    client,
                    url,
                    api_key,
                    prompt,
                    sequence=(batch_index * 100000) + index,
                )
                results.append(result)

        await asyncio.gather(*(worker(i) for i in range(batch_size)))

        if batch_index % report_every_batches == 0:
            current_elapsed = time.perf_counter() - started
            print(
                f"[soak] elapsed={current_elapsed:.1f}s batches={batch_index} total_requests={len(results)}"
            )

        if pause_seconds > 0:
            await asyncio.sleep(pause_seconds)

    elapsed = time.perf_counter() - started
    return _build_summary(results, elapsed)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run validate endpoint smoke/soak load checks"
    )
    parser.add_argument(
        "--mode", choices=("smoke", "soak"), default=os.getenv("MODE", "smoke")
    )
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("API_BASE_URL", "http://localhost:8000/api/v1"),
    )
    parser.add_argument("--api-key", default=os.getenv("API_KEY"))
    parser.add_argument(
        "--prompt", default=os.getenv("PROMPT", "What are your support hours?")
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.getenv("REQUEST_TIMEOUT", "15")),
    )

    parser.add_argument(
        "--total-requests", type=int, default=int(os.getenv("TOTAL_REQUESTS", "200"))
    )
    parser.add_argument(
        "--concurrency", type=int, default=int(os.getenv("CONCURRENCY", "10"))
    )

    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=int(os.getenv("DURATION_SECONDS", "1800")),
    )
    parser.add_argument(
        "--batch-size", type=int, default=int(os.getenv("BATCH_SIZE", "30"))
    )
    parser.add_argument(
        "--pause-seconds", type=float, default=float(os.getenv("PAUSE_SECONDS", "1"))
    )
    parser.add_argument(
        "--report-every-batches",
        type=int,
        default=int(os.getenv("REPORT_EVERY_BATCHES", "10")),
    )

    parser.add_argument(
        "--max-server-errors",
        type=int,
        default=int(os.getenv("MAX_SERVER_ERRORS", "0")),
    )
    parser.add_argument(
        "--max-p95-ms", type=float, default=float(os.getenv("MAX_P95_MS", "4000"))
    )
    parser.add_argument(
        "--max-ok-p95-ms",
        type=float,
        default=float(os.getenv("MAX_OK_P95_MS", "2500")),
    )
    parser.add_argument("--summary-json", default=os.getenv("SUMMARY_JSON"))
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    api_base_url = args.api_base_url.rstrip("/")
    api_key = args.api_key
    if not api_key:
        raise SystemExit("Missing API key. Pass --api-key or set API_KEY")

    url = f"{api_base_url}/validate"

    async with httpx.AsyncClient(timeout=args.request_timeout) as client:
        if args.mode == "smoke":
            summary = await _run_smoke(
                client,
                url=url,
                api_key=api_key,
                prompt=args.prompt,
                total_requests=args.total_requests,
                concurrency=args.concurrency,
            )
        else:
            summary = await _run_soak(
                client,
                url=url,
                api_key=api_key,
                prompt=args.prompt,
                duration_seconds=args.duration_seconds,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
                pause_seconds=args.pause_seconds,
                report_every_batches=max(1, args.report_every_batches),
            )

    _print_summary(summary, url=url, mode=args.mode, concurrency=args.concurrency)

    if args.summary_json:
        payload = {
            "mode": args.mode,
            "endpoint": url,
            "total_requests": summary.total_requests,
            "elapsed_seconds": summary.elapsed_seconds,
            "status_counts": dict(sorted(summary.status_counts.items())),
            "latency_ms": {
                "p50": summary.p50_ms,
                "p95": summary.p95_ms,
                "mean": summary.mean_ms,
            },
            "status_latency_ms": summary.status_latency_ms,
        }
        with open(args.summary_json, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
        print(f"Summary written to {args.summary_json}")

    passed, failures = _validate_thresholds(
        summary,
        max_server_errors=args.max_server_errors,
        max_p95_ms=args.max_p95_ms,
        max_ok_p95_ms=args.max_ok_p95_ms,
    )
    if not passed:
        print("\nFAILURE THRESHOLDS EXCEEDED:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
