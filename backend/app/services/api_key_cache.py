"""Small in-memory cache for API key verification results."""

from __future__ import annotations

import hashlib
import threading
import time

from app.config import settings


class ApiKeyVerifyCache:
    """Thread-safe TTL cache for API key verification outcomes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[bool, float]] = {}

    def _make_key(self, raw_api_key: str, persisted_hash: str) -> str:
        digest = hashlib.sha256(
            f"{raw_api_key}:{persisted_hash}".encode("utf-8")
        ).hexdigest()
        return digest

    def get(self, raw_api_key: str, persisted_hash: str) -> bool | None:
        key = self._make_key(raw_api_key, persisted_hash)
        now = time.time()
        with self._lock:
            cached = self._data.get(key)
            if not cached:
                return None

            value, expires_at = cached
            if expires_at <= now:
                self._data.pop(key, None)
                return None

            return value

    def set(self, raw_api_key: str, persisted_hash: str, value: bool) -> None:
        key = self._make_key(raw_api_key, persisted_hash)
        ttl = max(1, settings.api_key_verify_cache_ttl_seconds)
        expires_at = time.time() + ttl
        with self._lock:
            if len(self._data) >= max(1, settings.api_key_verify_cache_max_entries):
                # Evict oldest expiration first; fallback pop arbitrary if needed.
                oldest_key = min(self._data.items(), key=lambda item: item[1][1])[0]
                self._data.pop(oldest_key, None)

            self._data[key] = (value, expires_at)


api_key_verify_cache = ApiKeyVerifyCache()
