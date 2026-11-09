"""Who says yes to a mutating step. The agent never decides this for itself."""
from __future__ import annotations

from typing import Callable, Protocol

from sre_agent.domain.models import ApprovalRequest, Decision


class Approver(Protocol):
    def decide(self, request: ApprovalRequest) -> Decision: ...


class DenyAll:
    """Safe default: if nobody is wired up to approve, nothing mutating runs."""

    def decide(self, request: ApprovalRequest) -> Decision:
        return Decision(False, "policy", "no approver configured")


class ScriptedApprover:
    """Pre-recorded human answers, keyed by tool name. Used by the demo and tests."""

    def __init__(self, answers: dict[str, Decision], default: Decision | None = None) -> None:
        self.answers = answers
        self.default = default or Decision(False, "policy", "no scripted answer")
        self.seen: list[ApprovalRequest] = []

    def decide(self, request: ApprovalRequest) -> Decision:
        self.seen.append(request)
        return self.answers.get(request.tool, self.default)


class ConsoleApprover:
    """Ask a real person at the terminal."""

    def __init__(self, name: str = "on-call", ask: Callable[[str], str] = input) -> None:
        self.name, self._ask = name, ask

    def decide(self, request: ApprovalRequest) -> Decision:
        print(f"    >>> APPROVAL NEEDED  change: {request.preview}")
        answer = self._ask(f"    approve {request.tool} [{request.risk.value}]? (y/n + optional reason): ").strip()
        first, _, rest = answer.partition(" ")
        approved = first.lower() in ("y", "yes")
        reason = rest.strip() or ("approved" if approved else "denied")
        return Decision(approved, self.name, reason)
