"""Approval requests and decisions.

Three rules make an approval trustworthy:
- it is **bound to a fingerprint** of the exact action (change one argument and it no longer counts),
- the person who asked for the run **cannot approve it** (separation of duties),
- CRITICAL actions need **two different** approvers, and any single rejection wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .actions import Action
from .risk import Risk


class ApprovalError(ValueError):
    """A decision that must not be recorded."""


@dataclass(frozen=True)
class Decision:
    approver: str
    approve: bool
    comment: str
    fingerprint: str
    at: str


@dataclass
class ApprovalRequest:
    id: str
    run_id: str
    requested_by: str
    action: Action
    risk: Risk
    created_at: str
    decisions: list[Decision] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        return self.action.fingerprint()

    @property
    def status(self) -> str:
        if any(not d.approve for d in self.decisions):
            return "rejected"
        approvers = {d.approver for d in self.decisions if d.approve}
        return "approved" if len(approvers) >= self.risk.required_approvals else "pending"

    def decide(self, approver: str, approve: bool, comment: str, fingerprint: str, at: str) -> Decision:
        if self.status != "pending":
            raise ApprovalError(f"{self.id} is already {self.status}")
        if fingerprint != self.fingerprint:
            raise ApprovalError("decision refers to a different action (arguments changed since review)")
        if approver == self.requested_by:
            raise ApprovalError(f"{approver} started this run and cannot approve it")
        if any(d.approver == approver for d in self.decisions):
            raise ApprovalError(f"{approver} has already decided on {self.id}")
        if approve and self.risk.needs_reason and not comment.strip():
            raise ApprovalError(f"{self.risk.level.value} risk approvals need a written reason")
        decision = Decision(approver, approve, comment, fingerprint, at)
        self.decisions.append(decision)
        return decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "run_id": self.run_id, "requested_by": self.requested_by,
            "action": self.action.to_dict(), "risk": self.risk.to_dict(), "created_at": self.created_at,
            "decisions": [vars(d) for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        return cls(
            data["id"], data["run_id"], data["requested_by"], Action.from_dict(data["action"]),
            Risk.from_dict(data["risk"]), data["created_at"], [Decision(**d) for d in data["decisions"]],
        )
