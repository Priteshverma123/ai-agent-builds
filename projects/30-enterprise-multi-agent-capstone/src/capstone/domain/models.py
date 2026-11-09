"""Domain objects shared by every layer: plans, steps, findings, answers. No I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of a document, with enough metadata to cite it."""

    id: str
    source: str      # file name
    section: str     # markdown heading
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class Step:
    """One unit of delegated work: which specialist, and what to do."""

    agent: str
    instruction: str


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Citation:
    n: int
    source: str
    section: str


@dataclass
class Blackboard:
    """Shared memory the specialists read from and write to during one request."""

    question: str
    findings: list[Hit] = field(default_factory=list)
    quarantined: list[Hit] = field(default_factory=list)
    calculation: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None
    tools_used: list[str] = field(default_factory=list)
    draft: str = ""

    def citations(self) -> list[Citation]:
        return [Citation(i, h.chunk.source, h.chunk.section) for i, h in enumerate(self.findings, 1)]


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    text: str                      # possibly redacted
    reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------- HTTP contract
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class CitationOut(BaseModel):
    n: int
    source: str
    section: str


class AskResponse(BaseModel):
    answer: str
    blocked: bool
    citations: list[CitationOut]
    plan: list[str]
    tools_used: list[str]
    guardrail_notes: list[str]
    trace_id: str
