"""The approval-gated agent.

The model proposes; the agent scores the risk; low-risk actions run, everything else becomes an
`ApprovalRequest` and the run is checkpointed and paused. A human decides later (minutes or days),
and `resume()` continues exactly where the run stopped.

Two places enforce approval, on purpose:
- the agent loop never moves a risky action to execution without an approved request, and
- `Executor.run` re-checks at the boundary, so no other code path can skip the gate either.
"""

from __future__ import annotations

import json
import uuid
from typing import Callable

from .actions import TOOL_SPECS, Action, Backoffice, ToolSpec
from .approvals import ApprovalError, ApprovalRequest
from .audit import AuditLog
from .llm import LLM, parse_reply
from .risk import RiskPolicy
from .store import RunState, RunStore

Emit = Callable[[str, str, list[str]], None]

SYSTEM_PROMPT = """You are a customer-support operations agent. You can only PROPOSE actions.
Risky actions are reviewed by a human; a result with status="rejected" means a human said no:
do not retry it, adapt your plan. Tools:
{tools}
Reply with exactly ONE JSON object: {{"tool": "<name>", "args": {{...}}}} or {{"answer": "<summary>"}}."""


def _quiet(kind: str, title: str, lines: list[str]) -> None:
    return None


class Executor:
    """The only code that touches the back office."""

    def __init__(self, backoffice: Backoffice, policy: RiskPolicy, specs: dict[str, ToolSpec] = TOOL_SPECS) -> None:
        self.backoffice, self.policy, self.specs = backoffice, policy, specs

    def run(self, action: Action, idempotency_key: str, approval: ApprovalRequest | None) -> str:
        risk = self.policy.assess(action, self.specs[action.tool])
        if risk.required_approvals:
            if approval is None or approval.status != "approved" or approval.fingerprint != action.fingerprint():
                raise PermissionError(f"{action.describe()} is {risk.level.value} risk and has no matching approval")
        handler = getattr(self.backoffice, action.tool)
        return handler(**action.args, idempotency_key=idempotency_key)


class ApprovalAgent:
    def __init__(self, llm: LLM, executor: Executor, store: RunStore, audit: AuditLog,
                 emit: Emit = _quiet, max_steps: int = 10) -> None:
        self.llm, self.executor, self.store, self.audit = llm, executor, store, audit
        self.emit, self.max_steps = emit, max_steps
        tools = "\n".join(f"- {s.description}" for s in executor.specs.values())
        self.system = SYSTEM_PROMPT.format(tools=tools)

    # ------------------------------------------------------------------ public API

    def start(self, task: str, requested_by: str) -> RunState:
        state = RunState(id=f"run-{uuid.uuid4().hex[:8]}", task=task, requested_by=requested_by,
                         messages=[{"role": "user", "content": task}])
        self.audit.append("run_started", state.id, task=task, requested_by=requested_by)
        return self._drive(state)

    def resume(self, run_id: str) -> RunState:
        state = self.store.load(run_id)
        if state.status == "waiting_approval":
            state.status = "running"
        self.audit.append("run_resumed", run_id)
        return self._drive(state)

    def decide(self, run_id: str, approver: str, approve: bool, comment: str = "") -> ApprovalRequest:
        """Record one human decision on the run's pending request (does not resume the run)."""
        state = self.store.load(run_id)
        if not state.pending:
            raise ApprovalError(f"{run_id} has nothing waiting for approval")
        request = state.pending
        try:
            request.decide(approver, approve, comment, request.fingerprint, self.audit.clock())
        except ApprovalError as exc:
            self.audit.append("decision_refused", run_id, request=request.id, approver=approver, reason=str(exc))
            raise
        self.audit.append("approved" if approve else "rejected", run_id, request=request.id,
                          approver=approver, comment=comment, fingerprint=request.fingerprint)
        self.store.save(state)
        return request

    # ------------------------------------------------------------------ the loop

    def _drive(self, state: RunState) -> RunState:
        while state.status == "running":
            if state.in_flight:
                self._execute(state)
            elif state.pending:
                if not self._settle_pending(state):
                    return state
            elif state.step >= self.max_steps:
                self._finish(state, "failed", "Stopped: step limit reached.")
            else:
                self._think(state)
        return state

    def _think(self, state: RunState) -> None:
        reply = parse_reply(self.llm.complete(self.system, state.messages))
        state.step += 1
        state.messages.append({"role": "assistant", "content": json.dumps(reply)})
        if "answer" in reply:
            self._finish(state, "done", str(reply["answer"]))
            return

        action = Action(str(reply.get("tool")), dict(reply.get("args") or {}))
        spec = self.executor.specs.get(action.tool)
        if spec is None:
            self._observe(state, action.tool, "error", f"unknown tool {action.tool!r}")
            return
        risk = self.executor.policy.assess(action, spec)
        self.audit.append("proposed", state.id, step=state.step, action=action.to_dict(),
                          risk=risk.level.value, score=risk.score)
        self.emit("propose", f"step {state.step}: {action.describe()}", [f"risk {risk.level.value} ({risk.score}/100)"])

        if risk.required_approvals == 0:
            state.in_flight = {"action": action.to_dict(), "key": f"{state.id}:{state.step}"}
            return
        state.pending = ApprovalRequest(
            id=f"req-{state.step}", run_id=state.id, requested_by=state.requested_by,
            action=action, risk=risk, created_at=self.audit.clock(),
        )
        self.audit.append("approval_requested", state.id, request=state.pending.id,
                          fingerprint=state.pending.fingerprint, required=risk.required_approvals)

    def _settle_pending(self, state: RunState) -> bool:
        """Return False if the run must pause; otherwise move the request forward."""
        request = state.pending
        assert request is not None
        if request.status == "pending":
            state.status = "waiting_approval"
            self.store.save(state)
            self.emit("pause", f"PAUSED: {request.id} needs approval", [f"checkpoint saved: {state.id}"])
            return False
        if request.status == "approved":
            approvers = ", ".join(d.approver for d in request.decisions)
            self.emit("approved", f"{request.id} approved by {approvers}", [])
            state.in_flight = {"action": request.action.to_dict(), "key": f"{state.id}:{request.id}"}
            return True
        rejection = next(d for d in request.decisions if not d.approve)
        self.emit("rejected", f"{request.id} rejected by {rejection.approver}", [rejection.comment])
        state.pending = None
        self._observe(state, request.action.tool, "rejected", f"rejected by {rejection.approver}: {rejection.comment}")
        return True

    def _execute(self, state: RunState) -> None:
        flight = state.in_flight
        assert flight is not None
        action = Action.from_dict(flight["action"])
        approval = state.pending if state.pending and state.pending.fingerprint == action.fingerprint() else None
        self.store.save(state)  # commit the intent BEFORE the side effect
        try:
            result, status = self.executor.run(action, flight["key"], approval), "ok"
        except PermissionError as exc:
            result, status = str(exc), "blocked"
        self.audit.append("executed" if status == "ok" else "blocked", state.id,
                          action=action.to_dict(), key=flight["key"], result=result)
        self.emit("execute", f"{action.tool} -> {result[:60]}{'...' if len(result) > 60 else ''}", [])
        state.in_flight, state.pending = None, None
        self._observe(state, action.tool, status, result)

    def _observe(self, state: RunState, tool: str, status: str, body: str) -> None:
        state.messages.append({"role": "user",
                               "content": f'<tool_result name="{tool}" status="{status}">\n{body}\n</tool_result>'})
        self.store.save(state)

    def _finish(self, state: RunState, status: str, answer: str) -> None:
        state.status, state.answer = status, answer
        self.audit.append("run_finished", state.id, status=status, answer=answer)
        self.store.save(state)
        self.emit("done", answer, [])
