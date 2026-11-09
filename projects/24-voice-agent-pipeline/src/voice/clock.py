"""Clocks: a virtual one for deterministic simulation, a real one for live runs.

Latency is the whole point of a voice pipeline, so we need to measure it - but tests that sleep
for real are slow and flaky. :class:`VirtualClock` is an "autojump" clock: every component sleeps
through ``clock.sleep(ms)``; when every task is blocked, the clock jumps straight to the next
wake-up time. A 10-second conversation simulates in milliseconds, and the timings are exact and
repeatable. (The idea is the same as Trio's ``MockClock(autojump_threshold=0)``.)
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections.abc import Coroutine
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class Clock(Protocol):
    @property
    def now_ms(self) -> float: ...

    async def sleep(self, ms: float) -> None: ...

    def run(self, main: Coroutine[Any, Any, T]) -> T: ...


class RealClock:
    """Wall-clock time; used when a real model (with real network latency) is in the loop."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    @property
    def now_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    async def sleep(self, ms: float) -> None:
        await asyncio.sleep(max(ms, 0) / 1000)

    def run(self, main: Coroutine[Any, Any, T]) -> T:
        self._t0 = time.perf_counter()
        return asyncio.run(main)


class Deadlock(RuntimeError):
    """Every task is waiting, but nobody is sleeping - nothing can ever happen again."""


class VirtualClock:
    """Simulated time that advances only when all tasks are idle."""

    SETTLE_ROUNDS = 50  # loop iterations to let ready tasks run before we decide "everyone is idle"

    def __init__(self) -> None:
        self._now = 0.0
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._seq = itertools.count()

    @property
    def now_ms(self) -> float:
        return self._now

    async def sleep(self, ms: float) -> None:
        if ms <= 0:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._sleepers, (self._now + ms, next(self._seq), future))
        await future

    def run(self, main: Coroutine[Any, Any, T]) -> T:
        return asyncio.run(self._drive(main))

    async def _drive(self, main: Coroutine[Any, Any, T]) -> T:
        task = asyncio.ensure_future(main)
        while True:
            for _ in range(self.SETTLE_ROUNDS):
                await asyncio.sleep(0)
            if task.done():
                return task.result()
            while self._sleepers and self._sleepers[0][2].done():  # drop cancelled sleepers
                heapq.heappop(self._sleepers)
            if not self._sleepers:
                task.cancel()
                raise Deadlock(f"all tasks blocked at t={self._now:.0f} ms with nothing scheduled")
            wake_at = self._sleepers[0][0]
            self._now = wake_at
            while self._sleepers and self._sleepers[0][0] == wake_at:
                _, _, future = heapq.heappop(self._sleepers)
                if not future.done():
                    future.set_result(None)
