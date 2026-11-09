"""Shared state (a "blackboard") with a single writer.

Workers can *read* everything, but only the supervisor *writes*, by committing a
:class:`WorkerResult`. One writer means parallel workers can never clobber each other, and every
change is attributable: the ledger records which worker produced it and under which instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .messages import CodeArtifact, ResearchNotes, Review, WorkerResult


@dataclass
class LedgerEntry:
    step: int
    worker: str
    instruction: str
    summary: str


@dataclass
class SharedState:
    goal: str
    research: ResearchNotes | None = None
    code: CodeArtifact | None = None
    reviews: list[Review] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)

    @property
    def latest_review(self) -> Review | None:
        return self.reviews[-1] if self.reviews else None

    def commit(self, step: int, result: WorkerResult) -> None:
        """Apply one worker's proposal. Research merges; code and reviews append/replace by version."""
        if result.research is not None:
            self.research = result.research if self.research is None else self.research.merge(result.research)
        if result.code is not None:
            self.code = result.code
        if result.review is not None:
            self.reviews.append(result.review)
        self.ledger.append(LedgerEntry(step, result.worker, result.instruction, result.summary))

    def summary(self, step: int, max_steps: int) -> str:
        """The compact view the supervisor's model sees each turn."""
        if self.research:
            research = (f"{len(self.research.rules)} rules, {len(self.research.examples)} examples "
                        f"from [{', '.join(self.research.sources)}]")
        else:
            research = "none"
        code = f"v{self.code.version} by {self.code.author}" if self.code else "none"
        review = "none"
        if self.latest_review:
            r = self.latest_review
            review = (f"v{r.version} PASSED ({r.checked} checks)" if r.passed
                      else f"v{r.version} FAILED ({len(r.failures)} of {r.checked} checks)")
        return "\n".join([
            f"GOAL: {self.goal}",
            f"RESEARCH: {research}",
            f"CODE: {code}",
            f"REVIEW: {review}",
            f"STEPS USED: {step}/{max_steps}",
        ])
