"""Map-reduce research: plan -> parallel workers (search, fetch, extract) -> dedup -> report."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from pydantic import ValidationError

from .corpus import Fetcher, SearchIndex, TransientFetchError, terms
from .dedup import deduplicate
from .llm import LLM, extract_json
from .models import Doc, Finding, Plan, Report, Source, SubQuestion, WorkerReport

PLANNER_PROMPT = """Split the user's research question into 2-6 independent sub-questions that can be
researched in parallel. For each, give a short kebab-case id and 3-6 search keywords.
Reply with JSON only: {"subquestions": [{"id": "...", "question": "...", "keywords": ["..."]}]}"""

EXTRACTOR_PROMPT = """Extract factual claims from the document that answer the sub-question.
Quote sentences verbatim; do not paraphrase or add facts. Reply with JSON only: {"claims": ["..."]}"""

Log = Callable[[str, str], None]


def grounded(claim: str, doc: Doc) -> bool:
    """Keep only claims whose words really occur, in order, in the document (no invented facts)."""
    return " ".join(terms(claim)) in " ".join(terms(doc.body))


class Swarm:
    def __init__(self, index: SearchIndex, fetcher: Fetcher, planner: LLM, extractor: LLM,
                 docs_per_worker: int = 3, log: Log | None = None) -> None:
        self.index = index
        self.fetcher = fetcher
        self.planner = planner
        self.extractor = extractor
        self.docs_per_worker = docs_per_worker
        self.log = log or (lambda who, msg: None)

    async def run(self, question: str) -> Report:
        start = time.perf_counter()
        plan = await self.plan(question)
        self.log("planner", f"{len(plan.subquestions)} sub-questions: {', '.join(s.id for s in plan.subquestions)}")

        # MAP: one worker per sub-question, all at once. The fetcher's semaphore is the real limit.
        workers = await asyncio.gather(*(self.worker(sq) for sq in plan.subquestions))

        # REDUCE: flatten in plan order, merge near-duplicates, group by section.
        findings = [f for w in workers for f in w.findings]
        clusters = deduplicate(findings)
        sections = {sq.id: sorted((c for c in clusters if c.subq == sq.id), key=lambda c: -c.corroboration)
                    for sq in plan.subquestions}
        cited = list(dict.fromkeys(d for c in clusters for d in c.doc_ids))
        sources = [Source(doc_id=d, title=self.index.docs[d].title, url=self.index.docs[d].url) for d in cited]
        self.log("reducer", f"{len(findings)} findings -> {len(clusters)} unique claims from {len(sources)} sources")
        return Report(question=question, plan=plan, sections=sections, sources=sources, workers=workers,
                      raw_findings=len(findings), wall_ms=(time.perf_counter() - start) * 1000,
                      fetch_ms_total=self.fetcher.fetch_ms_total)

    async def plan(self, question: str) -> Plan:
        reply = await asyncio.to_thread(self.planner.complete, PLANNER_PROMPT, f"QUESTION: {question}")
        try:
            return Plan.model_validate(extract_json(reply))
        except (ValueError, ValidationError):
            self.log("planner", "invalid plan; falling back to a single worker on the whole question")
            return Plan(subquestions=[SubQuestion(id="main", question=question, keywords=terms(question)[:6])])

    async def worker(self, sq: SubQuestion) -> WorkerReport:
        start = time.perf_counter()
        report = WorkerReport(subq=sq.id)
        doc_ids = self.index.search(sq.keywords, k=self.docs_per_worker)
        self.log(sq.id, f"search -> {', '.join(doc_ids) or 'nothing'}")
        results = await asyncio.gather(*(self.fetcher.fetch(d) for d in doc_ids), return_exceptions=True)
        for doc_id, result in zip(doc_ids, results):
            if isinstance(result, TransientFetchError):
                report.failed[doc_id] = str(result)
                self.log(sq.id, f"FAILED {doc_id}: {result}")
                continue
            if isinstance(result, BaseException):
                raise result
            report.fetched.append(doc_id)
            report.findings += await self.extract(sq, result)
        report.elapsed_ms = (time.perf_counter() - start) * 1000
        self.log(sq.id, f"done: {len(report.findings)} findings from {len(report.fetched)} docs "
                        f"in {report.elapsed_ms:.0f} ms")
        return report

    async def extract(self, sq: SubQuestion, doc: Doc) -> list[Finding]:
        prompt = f"SUBQUESTION: {sq.question}\nKEYWORDS: {', '.join(sq.keywords)}\nDOCUMENT:\n{doc.body}"
        reply = await asyncio.to_thread(self.extractor.complete, EXTRACTOR_PROMPT, prompt)
        try:
            claims = [str(c) for c in extract_json(reply).get("claims", [])]
        except ValueError:
            self.log(sq.id, f"extractor returned no JSON for {doc.id}; skipping")
            return []
        kept = [c for c in claims if grounded(c, doc)]
        if len(kept) < len(claims):
            self.log(sq.id, f"dropped {len(claims) - len(kept)} ungrounded claim(s) from {doc.id}")
        return [Finding(claim=c, doc_id=doc.id, subq=sq.id) for c in kept]
