"""The research agent: plan queries -> search -> fetch -> extract notes -> write a cited brief.

This is a *workflow-shaped* agent: the code owns the loop and the budget, the model
owns the judgement calls (which queries, which facts matter, how to phrase the brief).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .corpus import LocalWeb, Page
from .llm import LLM, extract_json
from .sources import Note, SourceTracker
from .trace import Trace

PLAN_SYSTEM = """TASK: PLAN
You are a research planner. Break the question into 2-4 short web search queries that
together cover: what it is, the evidence, and the costs or drawbacks.
Reply with JSON only: {"queries": ["...", "..."]}"""

EXTRACT_SYSTEM = """TASK: EXTRACT
You read one web page and copy out at most 2 factual sentences that help answer the
question. Copy sentences verbatim; prefer sentences with numbers. If nothing is
relevant, return an empty list. Reply with JSON only: {"claims": ["...", "..."]}"""

WRITE_SYSTEM = """TASK: WRITE
Write a short research brief from the numbered notes only. Every bullet must end with
the citation of its note, like [2]. Never cite a number that is not in the notes.
Put claims from opinion sources under "Contested claims". Sections: Key findings,
Contested claims (if any), Bottom line."""


@dataclass
class ResearchConfig:
    results_per_query: int = 2
    max_fetches: int = 5  # the budget: real fetches cost time and money


@dataclass
class Brief:
    question: str
    text: str
    bibliography: list[str]
    fetched: int
    notes: list[Note] = field(default_factory=list)


class ResearchAgent:
    def __init__(self, web: LocalWeb, llm: LLM, config: ResearchConfig | None = None, trace: Trace | None = None) -> None:
        self.web = web
        self.llm = llm
        self.config = config or ResearchConfig()
        self.trace = trace or Trace(echo=False)

    def plan(self, question: str) -> list[str]:
        queries = extract_json(self.llm.complete(PLAN_SYSTEM, f"Question: {question}"))["queries"]
        self.trace.event("think", f"plan -> {len(queries)} search queries", [f"{i}. {q}" for i, q in enumerate(queries, 1)])
        return queries

    def extract(self, question: str, focus: str, page: Page) -> list[str]:
        prompt = f"Question: {question}\nFocus: {focus}\nSource:\n{page.body}"
        return list(extract_json(self.llm.complete(EXTRACT_SYSTEM, prompt))["claims"])

    def write(self, question: str, notes: list[Note], tracker: SourceTracker) -> str:
        lines = [f"[{n.source_id}] ({tracker.pages[n.source_id].kind}) {n.claim}" for n in notes]
        return self.llm.complete(WRITE_SYSTEM, f"Question: {question}\nNotes:\n" + "\n".join(lines))

    def run(self, question: str) -> Brief:
        tracker, notes = SourceTracker(), []
        self.trace.box("WEB RESEARCH AGENT", [f"Q: {question}", f"model: {self.llm.name} | budget: {self.config.max_fetches} fetches"])

        for query in self.plan(question):
            results = self.web.search(query, k=self.config.results_per_query)
            self.trace.event("tool", f'search("{query}")', [f"{r.score:5.2f}  {r.url}" for r in results] or ["(no results)"])
            for result in results:
                if len(tracker.visited) >= self.config.max_fetches:
                    self.trace.event("skip", f"budget reached, not fetching {result.url}")
                    continue
                if not tracker.visit(result.url):
                    self.trace.event("skip", f"already read {result.url}")
                    continue
                page = self.web.fetch(result.url)
                claims = self.extract(question, query, page)
                if not claims:
                    self.trace.event("read", f"fetch {result.url}", ["no relevant facts -> not cited"])
                    continue
                source_id = tracker.cite(page)
                notes += [Note(source_id, claim) for claim in claims if Note(source_id, claim) not in notes]
                self.trace.event("read", f"fetch {result.url}  -> source [{source_id}] ({page.kind})", [f'"{c}"' for c in claims])

        draft = self.write(question, notes, tracker)
        text, dropped = tracker.remove_unverified_lines(draft)
        self.trace.event("check", f"citations verified: {len(tracker.pages)} sources, {dropped} unsupported line(s) removed")
        self.trace.blank()
        self.trace.box("RESEARCH BRIEF", [question, "", *text.splitlines(), "", "Sources", *tracker.bibliography()])
        return Brief(question, text, tracker.bibliography(), fetched=len(tracker.visited), notes=notes)
