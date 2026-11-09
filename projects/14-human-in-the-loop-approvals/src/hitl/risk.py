"""Risk scoring: turn an action into a 0-100 score, a level, and human-readable reasons.

The reasons matter as much as the score: an approver who sees *why* something is risky makes a
better decision than one who sees only "HIGH".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .actions import Action, ToolSpec


class Level(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# How many distinct humans must say yes before the action may run.
APPROVALS_REQUIRED = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 1, Level.CRITICAL: 2}


@dataclass(frozen=True)
class Risk:
    score: int
    level: Level
    reasons: tuple[str, ...]

    @property
    def required_approvals(self) -> int:
        return APPROVALS_REQUIRED[self.level]

    @property
    def needs_reason(self) -> bool:
        """HIGH and CRITICAL approvals must explain themselves in the audit log."""
        return self.level in (Level.HIGH, Level.CRITICAL)

    def to_dict(self) -> dict:
        return {"score": self.score, "level": self.level.value, "reasons": list(self.reasons)}

    @classmethod
    def from_dict(cls, data: dict) -> "Risk":
        return cls(data["score"], Level(data["level"]), tuple(data["reasons"]))


@dataclass(frozen=True)
class RiskPolicy:
    company_domains: tuple[str, ...] = ("acme.example",)
    large_amount: float = 100.0
    very_large_amount: float = 1000.0

    def assess(self, action: Action, spec: ToolSpec) -> Risk:
        score = spec.base_risk
        reasons = [f"base risk for {spec.category}: {spec.base_risk}"]

        amount = action.args.get("amount")
        if isinstance(amount, (int, float)):
            if amount > self.very_large_amount:
                score += 35
                reasons.append(f"amount {amount:.2f} > {self.very_large_amount:.2f}: +35")
            elif amount > self.large_amount:
                score += 20
                reasons.append(f"amount {amount:.2f} > {self.large_amount:.2f}: +20")

        recipient = str(action.args.get("to", ""))
        if recipient and recipient.rpartition("@")[2] not in self.company_domains:
            score += 15
            reasons.append(f"external recipient {recipient}: +15")

        if not spec.reversible:
            score += 25
            reasons.append("cannot be undone: +25")
        if action.args.get("purge_data") is True:
            score += 15
            reasons.append("deletes customer data: +15")

        score = min(score, 100)
        return Risk(score, _level(score), tuple(reasons))


def _level(score: int) -> Level:
    if score < 30:
        return Level.LOW
    if score < 60:
        return Level.MEDIUM
    if score < 80:
        return Level.HIGH
    return Level.CRITICAL
