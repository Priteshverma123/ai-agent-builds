"""Token-bucket rate limiting, one bucket per tenant.

A bucket holds up to `capacity` tokens (the burst) and refills continuously at `rate` tokens/second.
Each request spends one token. Empty bucket -> 429 with an exact Retry-After.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from gateway.adapters.clock import Clock
from gateway.domain.errors import RateLimited
from gateway.domain.models import Tenant


@dataclass
class TokenBucket:
    capacity: float
    rate: float  # tokens per second
    tokens: float
    updated_at: float

    def refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated_at = now

    def seconds_until_token(self) -> float:
        return 0.0 if self.tokens >= 1 else (1 - self.tokens) / self.rate


class RateLimiter:
    """Thread-safe: FastAPI runs sync endpoints on a thread pool, so two requests can race here."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _bucket(self, tenant: Tenant) -> TokenBucket:
        bucket = self._buckets.get(tenant.id)
        if bucket is None:
            plan = tenant.plan
            bucket = TokenBucket(plan.burst, plan.requests_per_minute / 60, plan.burst, self._clock.now())
            self._buckets[tenant.id] = bucket
        return bucket

    def acquire(self, tenant: Tenant) -> float:
        """Spend one token or raise RateLimited. Returns tokens left (for X-RateLimit-Remaining)."""
        with self._lock:
            bucket = self._bucket(tenant)
            bucket.refill(self._clock.now())
            if bucket.tokens < 1:
                wait = bucket.seconds_until_token()
                raise RateLimited(f"rate limit for '{tenant.id}' exceeded, retry in {wait:.1f}s", wait)
            bucket.tokens -= 1
            return bucket.tokens

    def remaining(self, tenant: Tenant) -> int:
        with self._lock:
            bucket = self._bucket(tenant)
            bucket.refill(self._clock.now())
            return int(bucket.tokens)
