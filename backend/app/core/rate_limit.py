"""Rate limit key derivation for SlowAPI."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def build_rate_limit_key(request: Request) -> str:
    """Bucket by API key when present, otherwise fallback to client IP."""
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


limiter = Limiter(key_func=build_rate_limit_key)


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a stable JSON payload for throttled requests."""
    if isinstance(exc, RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded",
                "error": "too_many_requests",
            },
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected rate limiter error"},
    )
