"""Simulated incident clock: the demo replays 14:12 onwards without waiting real minutes."""
from __future__ import annotations

from datetime import datetime, timedelta


class SimClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, minutes: float) -> None:
        self._now += timedelta(minutes=minutes)
