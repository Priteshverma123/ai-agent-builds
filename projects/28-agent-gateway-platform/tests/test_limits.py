"""Token bucket and budget ledger, including behaviour under thread contention."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import make_tenant
from gateway.adapters.clock import FakeClock
from gateway.domain.errors import BudgetExceeded, RateLimited
from gateway.services.budget import BudgetLedger
from gateway.services.ratelimit import RateLimiter


def test_bucket_allows_burst_then_blocks_with_retry_after() -> None:
    clock = FakeClock()
    limiter, tenant = RateLimiter(clock), make_tenant(burst=3, rpm=6)  # 1 token per 10 s
    for _ in range(3):
        limiter.acquire(tenant)
    with pytest.raises(RateLimited) as err:
        limiter.acquire(tenant)
    assert err.value.retry_after_s == pytest.approx(10.0)
    assert err.value.headers["Retry-After"] == "10"


def test_bucket_refills_continuously_but_never_above_capacity() -> None:
    clock = FakeClock()
    limiter, tenant = RateLimiter(clock), make_tenant(burst=3, rpm=6)
    for _ in range(3):
        limiter.acquire(tenant)
    clock.advance(10)
    limiter.acquire(tenant)  # exactly one token came back
    with pytest.raises(RateLimited):
        limiter.acquire(tenant)
    clock.advance(3_600)
    assert limiter.remaining(tenant) == 3


def test_bucket_admits_exactly_burst_under_concurrency() -> None:
    limiter, tenant = RateLimiter(FakeClock()), make_tenant(burst=25)
    admitted, lock = [], threading.Lock()

    def hit(_: int) -> None:
        try:
            limiter.acquire(tenant)
            with lock:
                admitted.append(1)
        except RateLimited:
            pass

    with ThreadPoolExecutor(max_workers=50) as pool:
        list(pool.map(hit, range(500)))
    assert len(admitted) == 25


def test_budget_reserve_commit_release() -> None:
    ledger, tenant = BudgetLedger(), make_tenant(budget=1.0)
    r1 = ledger.reserve(tenant, 0.6)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(tenant, 0.5)  # 0.6 reserved + 0.5 > 1.0
    ledger.commit(r1, 0.2)  # actual was cheaper than worst case
    assert ledger.spent("t1") == pytest.approx(0.2)
    r2 = ledger.reserve(tenant, 0.5)
    ledger.release(r2)  # provider failed: nothing is charged
    assert ledger.remaining(tenant) == pytest.approx(0.8)


def test_budget_commit_is_capped_at_reservation() -> None:
    ledger, tenant = BudgetLedger(), make_tenant(budget=1.0)
    r = ledger.reserve(tenant, 0.3)
    ledger.commit(r, 0.9)  # a misbehaving provider over-reports usage
    assert ledger.spent("t1") == pytest.approx(0.3)


def test_budget_hard_stop_holds_under_concurrency() -> None:
    ledger, tenant = BudgetLedger(), make_tenant(budget=1.0)

    def spend(_: int) -> bool:
        try:
            r = ledger.reserve(tenant, 0.03)
        except BudgetExceeded:
            return False
        ledger.commit(r, 0.03)
        return True

    with ThreadPoolExecutor(max_workers=40) as pool:
        ok = sum(pool.map(spend, range(400)))
    assert ok == 33
    assert ledger.spent("t1") <= 1.0
