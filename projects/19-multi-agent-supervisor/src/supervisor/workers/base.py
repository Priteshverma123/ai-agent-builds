"""The contract every worker implements."""

from __future__ import annotations

from typing import Protocol

from ..messages import WorkerName, WorkerResult
from ..state import SharedState


class Worker(Protocol):
    name: WorkerName
    description: str
    parallel_safe: bool  # may several copies run at once? (true for read-only work)

    async def run(self, instruction: str, state: SharedState) -> WorkerResult: ...
