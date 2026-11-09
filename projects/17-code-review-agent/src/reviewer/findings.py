"""Findings, ranking and the review verdict."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    confidence: float  # 0..1: how sure the check is that this is a real problem
    file: str
    line: int
    message: str
    suggestion: str = ""
    source: str = "static"  # static | llm

    @property
    def id(self) -> str:
        return f"{self.rule}@{self.file}:{self.line}"

    @property
    def rank(self) -> float:
        """Severity first, confidence breaks ties: a certain MEDIUM beats a doubtful one."""
        return int(self.severity) + self.confidence * 0.99

    def to_dict(self) -> dict:
        return {**asdict(self), "severity": self.severity.name, "id": self.id}


def rank(findings: list[Finding]) -> list[Finding]:
    """De-duplicate (same rule, file and line) and sort most important first."""
    unique: dict[str, Finding] = {}
    for f in findings:
        if f.id not in unique or f.rank > unique[f.id].rank:
            unique[f.id] = f
    return sorted(unique.values(), key=lambda f: (-f.rank, f.file, f.line))


def verdict(findings: list[Finding]) -> str:
    worst = max((f.severity for f in findings), default=Severity.INFO)
    if worst >= Severity.HIGH:
        return "REQUEST_CHANGES"
    if worst == Severity.MEDIUM:
        return "COMMENT"
    return "APPROVE"
