"""The supervisor: decide -> delegate (maybe in parallel) -> commit -> repeat -> merge.

The model only *proposes* the next move. The supervisor code validates it (known worker? allowed
to run in parallel? within budget?) and falls back to a deterministic policy when the proposal is
unusable. The final verdict comes from evidence in shared state, not from the model saying "done".
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from .llm import LLM, extract_json
from .messages import Decision, Delegation
from .state import LedgerEntry, SharedState
from .trace import Tracer
from .workers import Worker

SYSTEM_PROMPT = """You are the supervisor of a small engineering team. You never do the work yourself;
you decide who acts next. Workers:
{roster}
Rules: research before coding; every new code version must be reviewed; send failed reviews back to
the coder; finish only when the latest code passed review. You may delegate to several workers at
once only if they are marked parallel-safe.
Reply with JSON only:
{{"next": [{{"worker": "<name>", "instruction": "<what to do>"}}], "reason": "<why>"}}
or {{"next": "FINISH", "reason": "<why>"}}"""


@dataclass
class Limits:
    max_steps: int = 8
    max_visits: dict[str, int] = field(default_factory=lambda: {"coder": 3})


@dataclass
class Deliverable:
    """The merged output of the whole team."""

    goal: str
    status: Literal["approved", "incomplete"]
    reason: str
    code: str | None
    version: int | None
    sources: list[str]
    rules: list[str]
    checks: int
    steps: int
    ledger: list[LedgerEntry]


class InvalidDecision(ValueError):
    """The model proposed something the supervisor is not allowed to execute."""


class Supervisor:
    def __init__(self, workers: list[Worker], llm: LLM, limits: Limits | None = None,
                 tracer: Tracer | None = None) -> None:
        self.workers = {w.name: w for w in workers}
        self.llm = llm
        self.limits = limits or Limits()
        self.trace = tracer or Tracer()
        roster = "\n".join(f"- {w.name}: {w.description} (parallel-safe: {'yes' if w.parallel_safe else 'no'})"
                           for w in workers)
        self.system_prompt = SYSTEM_PROMPT.format(roster=roster)

    async def run(self, goal: str) -> Deliverable:
        state = SharedState(goal)
        visits: Counter[str] = Counter()
        steps = 0
        stop_reason = f"step budget of {self.limits.max_steps} exhausted"
        while steps < self.limits.max_steps:
            decision = self.decide(state, steps)
            if decision.finish:
                self.trace.log("FINISH", f"[{decision.source}] {decision.reason}")
                stop_reason = decision.reason
                break
            over = [d.worker for d in decision.delegations
                    if visits[d.worker] + 1 > self.limits.max_visits.get(d.worker, self.limits.max_steps)]
            if over:
                stop_reason = f"{over[0]} visit budget exhausted"
                self.trace.log("STOP", stop_reason)
                break
            steps += 1
            visits.update(d.worker for d in decision.delegations)
            await self._dispatch(steps, decision, state)
        return self.merge(state, steps, stop_reason)

    def decide(self, state: SharedState, step: int) -> Decision:
        """Ask the model; validate; fall back to the rule-based policy if anything is off."""
        prompt = state.summary(step, self.limits.max_steps)
        try:
            decision = self.parse(self.llm.complete(self.system_prompt, prompt))
            self.validate(decision)
            return decision
        except ValueError as exc:  # pydantic's ValidationError is a ValueError too
            self.trace.log("FALLBACK", f"model decision rejected ({_explain(exc)}); using rule-based routing")
            return fallback_policy(state)

    @staticmethod
    def parse(reply: str) -> Decision:
        data = extract_json(reply)
        if data.get("next") == "FINISH":
            return Decision(finish=True, reason=data.get("reason", ""))
        return Decision(delegations=data.get("next") or [], reason=data.get("reason", ""))

    def validate(self, decision: Decision) -> None:
        for d in decision.delegations:
            if d.worker not in self.workers:
                raise InvalidDecision(f"unknown worker {d.worker!r}")
        if len(decision.delegations) > 1:
            unsafe = [d.worker for d in decision.delegations if not self.workers[d.worker].parallel_safe]
            if unsafe:
                raise InvalidDecision(f"{unsafe[0]} is not parallel-safe")

    async def _dispatch(self, step: int, decision: Decision, state: SharedState) -> None:
        names = [d.worker for d in decision.delegations]
        mode = f" x{len(names)} in parallel" if len(names) > 1 else ""
        self.trace.log(f"STEP {step}", f"-> {', '.join(dict.fromkeys(names))}{mode}  [{decision.source}]",
                       f"why: {decision.reason}")
        results = await asyncio.gather(*(self.workers[d.worker].run(d.instruction, state)
                                         for d in decision.delegations))
        for delegation, result in zip(decision.delegations, results):
            state.commit(step, result)
            self.trace.log(f"  {result.worker}", f'"{delegation.instruction}"', f"=> {result.summary}")
        if len(results) > 1 and state.research:
            self.trace.log("  merge", f"research now {len(state.research.rules)} rules, "
                                      f"{len(state.research.examples)} examples from {len(state.research.sources)} sources")

    @staticmethod
    def merge(state: SharedState, steps: int, reason: str) -> Deliverable:
        """Assemble the team's output. 'approved' requires a passing review of the *latest* code."""
        review = state.latest_review
        approved = bool(state.code and review and review.passed and review.version == state.code.version)
        return Deliverable(
            goal=state.goal,
            status="approved" if approved else "incomplete",
            reason=reason,
            code=state.code.source if state.code else None,
            version=state.code.version if state.code else None,
            sources=state.research.sources if state.research else [],
            rules=state.research.rules if state.research else [],
            checks=review.checked if review else 0,
            steps=steps,
            ledger=state.ledger,
        )


def _explain(exc: ValueError) -> str:
    """One readable line, naming the offending value for validation errors."""
    if isinstance(exc, ValidationError):
        err = exc.errors()[0]
        return f"{'.'.join(map(str, err['loc']))}: {err['msg']} (got {err['input']!r})"
    return str(exc).splitlines()[0]


def fallback_policy(state: SharedState) -> Decision:
    """Deterministic routing used when the model's proposal can't be trusted."""
    review = state.latest_review
    if state.research is None:
        return Decision(delegations=[
            Delegation(worker="researcher", instruction=f"Find the style guide rules for: {state.goal}"),
            Delegation(worker="researcher", instruction=f"Find examples and acceptance tests for: {state.goal}"),
        ], reason="no research yet: gather rules and acceptance tests", source="fallback")
    if state.code is None:
        return Decision(delegations=[Delegation(worker="coder", instruction="Implement the goal")],
                        reason="no code yet", source="fallback")
    if review is None or review.version != state.code.version:
        return Decision(delegations=[Delegation(worker="reviewer", instruction="Review the latest code")],
                        reason="latest code is unreviewed", source="fallback")
    if not review.passed:
        return Decision(delegations=[Delegation(worker="coder", instruction="Fix the review failures")],
                        reason="review failed", source="fallback")
    return Decision(finish=True, reason="latest code passed review", source="fallback")
