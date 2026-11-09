"""Typed messages that flow between the supervisor and its workers.

Agents talking in free text is how multi-agent systems turn into a game of telephone. Here every
hop is a pydantic model: the supervisor emits :class:`Decision` / :class:`Delegation`, workers
return :class:`WorkerResult`, and the payloads (:class:`ResearchNotes`, :class:`CodeArtifact`,
:class:`Review`) are the only things allowed into shared state.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

WorkerName = Literal["researcher", "coder", "reviewer"]


class Example(BaseModel):
    """One acceptance test: ``slugify(given) == expected``."""

    given: str
    expected: str


class ResearchNotes(BaseModel):
    rules: list[str] = []
    examples: list[Example] = []
    sources: list[str] = []

    def merge(self, other: ResearchNotes) -> ResearchNotes:
        """Combine notes from parallel researchers, dropping duplicates but keeping order."""
        seen_examples = {(e.given, e.expected) for e in self.examples}
        return ResearchNotes(
            rules=self.rules + [r for r in other.rules if r not in self.rules],
            examples=self.examples + [e for e in other.examples if (e.given, e.expected) not in seen_examples],
            sources=self.sources + [s for s in other.sources if s not in self.sources],
        )


class CodeArtifact(BaseModel):
    version: int
    source: str
    author: str = "coder"


class Review(BaseModel):
    version: int
    passed: bool
    failures: list[str] = []
    checked: int = 0


class Delegation(BaseModel):
    worker: WorkerName
    instruction: str = Field(min_length=3)


class Decision(BaseModel):
    """What the supervisor wants next: one or more delegations, or finish."""

    delegations: list[Delegation] = []
    finish: bool = False
    reason: str = ""
    source: Literal["llm", "fallback"] = "llm"

    @model_validator(mode="after")
    def _finish_or_delegate(self) -> Decision:
        if self.finish == bool(self.delegations):
            raise ValueError("a decision must either finish or delegate (not both, not neither)")
        return self


class WorkerResult(BaseModel):
    """A worker's proposal. Workers never write shared state directly; the supervisor commits."""

    worker: WorkerName
    instruction: str
    summary: str
    research: ResearchNotes | None = None
    code: CodeArtifact | None = None
    review: Review | None = None
    ok: bool = True
