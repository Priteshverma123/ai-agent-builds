"""The durable execution engine: checkpointed steps, retries, leases, replay.

A workflow is ordinary ``async`` Python that calls ``await ctx.step(name, fn)`` for every piece of
work that touches the world (tools, LLM calls, side effects). For each step the engine:

1. **replays** - if the journal already has a result for ``name``, return it without running ``fn``;
2. **runs** - otherwise call ``fn`` with a stable idempotency key, retrying transient errors with
   exponential backoff;
3. **commits** - write the JSON result to the journal. Only now is the step "done".

If the process dies between 2 and 3, the step runs again on resume. That's why every side effect
must be idempotent (same key -> same outcome), and why the key is derived from ``run_id`` + step
name rather than from anything random.
"""

from __future__ import annotations

import asyncio
import itertools
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn

from .store import Journal, LeaseHeld
from .world import TransientError

Phase = Literal["before", "after_effect"]
Log = Callable[[str, str], None]


@dataclass(frozen=True)
class StepInfo:
    run_id: str
    name: str
    attempt: int

    @property
    def idempotency_key(self) -> str:
        """Stable across retries *and* across processes: the whole trick."""
        return f"{self.run_id}/{self.name}"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_s: float = 0.02
    retry_on: tuple[type[BaseException], ...] = (TransientError, TimeoutError)

    def delay(self, attempt: int) -> float:
        return self.base_delay_s * 2 ** (attempt - 1)


class SimulatedCrash(BaseException):
    """Raised to imitate the process dying. A BaseException, so no ``except Exception`` swallows it."""


@dataclass
class CrashPlan:
    """Kill the worker at a precise point: ``before`` a step runs, or ``after_effect`` - after the step
    did its work but before the journal commit (the nastiest moment for side effects)."""

    step: str
    phase: Phase = "after_effect"
    hard: bool = False  # True: os._exit like a real crash (no cleanup, no finally blocks)

    def check(self, step: str, phase: Phase) -> None:
        if step == self.step and phase == self.phase:
            if self.hard:
                os._exit(137)
            raise SimulatedCrash(f"crash at {step}:{phase}")


class StepFailed(RuntimeError):
    def __init__(self, step: str, error: str) -> None:
        super().__init__(f"step {step!r} failed: {error}")
        self.step = step
        self.error = error


@dataclass
class Context:
    """What a workflow function sees. Its only way to touch the world is :meth:`step`."""

    journal: Journal
    run_id: str
    owner: str
    lease_s: float
    log: Log
    crash: CrashPlan | None = None
    seen: set[str] = field(default_factory=set)

    async def step(self, name: str, fn: Callable[[StepInfo], Awaitable[Any]], *,
                   retry: RetryPolicy = RetryPolicy(), timeout_s: float = 10.0) -> Any:
        if name in self.seen:
            raise ValueError(f"step name {name!r} used twice; names must be unique and deterministic")
        self.seen.add(name)

        found, result = self.journal.get_step(self.run_id, name)
        if found:
            self.log("REPLAY", f"{name:<14} result from journal, not re-executed")
            return result

        for attempt in itertools.count(1):
            self._maybe_crash(name, "before")
            try:
                result = await asyncio.wait_for(fn(StepInfo(self.run_id, name, attempt)), timeout_s)
            except retry.retry_on as exc:
                if attempt == retry.max_attempts:
                    self._fail(name, f"{type(exc).__name__}: {exc} (after {attempt} attempts)", attempt)
                self.log("RETRY", f"{name:<14} attempt {attempt} failed ({exc}); backing off {retry.delay(attempt):.2f}s")
                await asyncio.sleep(retry.delay(attempt))
                continue
            except Exception as exc:  # noqa: BLE001 - anything else is permanent
                self._fail(name, f"{type(exc).__name__}: {exc}", attempt)
            self._maybe_crash(name, "after_effect")
            self.journal.complete_step(self.run_id, name, result, attempt)
            self.journal.claim(self.run_id, self.owner, self.lease_s)  # heartbeat: extend our lease
            self.log("STEP", f"{name:<14} done (attempt {attempt}) -> journaled")
            return result

    def _maybe_crash(self, name: str, phase: Phase) -> None:
        if self.crash:
            if self.crash.step == name and self.crash.phase == phase:
                self.log("CRASH", f"{name:<14} worker dies {'after the side effect, before the commit' if phase == 'after_effect' else 'before running'}")
            self.crash.check(name, phase)

    def _fail(self, name: str, error: str, attempts: int) -> NoReturn:
        self.journal.fail_step(self.run_id, name, error, attempts)
        self.log("FAILED", f"{name:<14} {error}")
        raise StepFailed(name, error)


Workflow = Callable[..., Awaitable[Any]]


class Engine:
    """Starts and resumes runs. Any number of engines (processes) can share one journal."""

    def __init__(self, journal: Journal, workflows: dict[str, Workflow], owner: str, *,
                 lease_s: float = 5.0, log: Log | None = None, crash: CrashPlan | None = None) -> None:
        self.journal = journal
        self.workflows = workflows
        self.owner = owner
        self.lease_s = lease_s
        self.log = log or (lambda kind, msg: None)
        self.crash = crash

    def start(self, workflow: str, **input: Any) -> str:
        if workflow not in self.workflows:
            raise KeyError(f"unknown workflow {workflow!r}")
        return self.journal.create_run(workflow, input)

    async def run(self, run_id: str) -> Any:
        """Execute (or resume) a run to completion. Safe to call again after any crash."""
        record = self.journal.get_run(run_id)
        if record.status == "completed":
            self.log("DONE", f"{run_id} already completed; returning the journaled result")
            return record.result
        if record.status == "failed":
            raise StepFailed("<run>", record.error or "run failed earlier")
        self.journal.claim(run_id, self.owner, self.lease_s)
        self.log("CLAIM", f"{run_id} leased by {self.owner} for {self.lease_s:.1f}s")
        ctx = Context(self.journal, run_id, self.owner, self.lease_s, self.log, self.crash)
        try:
            result = await self.workflows[record.workflow](ctx, **record.input)
        except StepFailed as exc:
            self.journal.fail(run_id, str(exc))
            raise
        self.journal.finish(run_id, result)
        self.log("DONE", f"{run_id} completed")
        return result

    async def run_when_free(self, run_id: str, poll_s: float = 0.1, max_wait_s: float = 30.0) -> Any:
        """What a worker pool does: if another worker's lease is live, wait for it to expire, then resume."""
        waited = 0.0
        while True:
            try:
                return await self.run(run_id)
            except LeaseHeld as exc:
                if waited >= max_wait_s:
                    raise
                if waited == 0:
                    self.log("WAIT", f"{exc}; a crashed worker never renews, so we wait")
                await asyncio.sleep(poll_s)
                waited += poll_s
