"""In-memory token-bucket rate limiting (per client key).

Suitable for a single gateway process on the pilot host. Keys are usually
``ip:<addr>`` or ``user:<username>`` / ``token:<prefix>``.
"""

import asyncio
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """Return True if the request is within the limit."""
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=limit - 1, updated=now)
                self._prune_locked(now)
                return True

            elapsed = now - bucket.updated
            refill = elapsed * (limit / window_seconds)
            bucket.tokens = min(float(limit), bucket.tokens + refill)
            bucket.updated = now

            if bucket.tokens < 1.0:
                return False
            bucket.tokens -= 1.0
            self._prune_locked(now)
            return True

    def _prune_locked(self, now: float) -> None:
        if len(self._buckets) <= 5000:
            return
        stale = [k for k, b in self._buckets.items() if now - b.updated > 3600]
        for key in stale[:2000]:
            del self._buckets[key]


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter


def client_ip(request) -> str:
    """Prefer X-Forwarded-For only when explicitly trusted upstream."""
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"
