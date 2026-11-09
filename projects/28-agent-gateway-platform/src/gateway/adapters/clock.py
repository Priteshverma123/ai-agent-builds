"""Time as a dependency. Rate limiters and caches are untestable if they call time.time() directly."""
from __future__ import annotations

import threading
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    """Monotonic seconds: immune to wall-clock jumps (NTP, daylight saving)."""

    def now(self) -> float:
        return time.monotonic()


class FakeClock:
    """A clock you move by hand. Used by tests and by the demo so output is reproducible."""

    def __init__(self, start: float = 1_000.0) -> None:
        self._t = start
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._t += seconds
