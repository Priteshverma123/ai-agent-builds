"""Typed records that flow through the swarm: plan -> findings -> clusters -> report."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    """One slice of the research question, owned by one worker."""

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    question: str
    keywords: list[str] = Field(min_length=1)


class Plan(BaseModel):
    subquestions: list[SubQuestion] = Field(min_length=1, max_length=8)


class Doc(BaseModel):
    id: str
    title: str
    url: str
    body: str
    latency_ms: int = 50
    flaky: bool = False


class Finding(BaseModel):
    """A claim one worker extracted from one document."""

    claim: str
    doc_id: str
    subq: str


class Source(BaseModel):
    doc_id: str
    title: str
    url: str


class Cluster(BaseModel):
    """Findings that say the same thing, merged. More sources = better corroborated."""

    claim: str
    subq: str
    doc_ids: list[str]
    variants: int = 1

    @property
    def corroboration(self) -> int:
        return len(self.doc_ids)


class WorkerReport(BaseModel):
    subq: str
    findings: list[Finding] = []
    fetched: list[str] = []
    failed: dict[str, str] = {}  # doc_id -> reason
    elapsed_ms: float = 0.0


class Report(BaseModel):
    question: str
    plan: Plan
    sections: dict[str, list[Cluster]]
    sources: list[Source]
    workers: list[WorkerReport]
    raw_findings: int
    wall_ms: float
    fetch_ms_total: float
