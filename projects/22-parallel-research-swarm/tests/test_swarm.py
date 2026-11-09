"""Swarm behaviour: real parallelism, bounded concurrency, single-flight, retries, dedup, grounding."""

import asyncio
import json
from pathlib import Path

import pytest

from swarm.cli import QUESTION, build_swarm
from swarm.corpus import Fetcher, SearchIndex, TransientFetchError, load_corpus
from swarm.dedup import deduplicate, jaccard, shingles
from swarm.llm import MockExtractor, MockPlanner
from swarm.models import Doc, Finding
from swarm.report import render_markdown
from swarm.swarm import Swarm, grounded

CORPUS = Path(__file__).resolve().parents[1] / "examples" / "corpus"
ORIGINAL = "A typical 10 kWh home battery costs between $8,000 and $14,000 installed in 2026."
MIRROR = "A typical 10 kWh home battery costs between $8,000 and $14,000 installed, as of 2026."


@pytest.fixture(scope="module")
def run_demo():
    swarm = build_swarm()
    report = asyncio.run(swarm.run(QUESTION))
    return swarm, report


# --- dedup -----------------------------------------------------------------------------------

def test_near_duplicates_are_similar_and_unrelated_claims_are_not():
    assert jaccard(shingles(ORIGINAL), shingles(MIRROR)) >= 0.5
    assert jaccard(shingles(ORIGINAL), shingles("Payback periods of 8 to 12 years are common.")) < 0.1


def test_dedup_merges_mirrors_and_keeps_every_source():
    findings = [Finding(claim=ORIGINAL, doc_id="a", subq="cost"), Finding(claim=MIRROR, doc_id="b", subq="cost"),
                Finding(claim="Installation labour adds roughly $1,000.", doc_id="c", subq="cost")]
    clusters = deduplicate(findings)
    assert len(clusters) == 2
    assert clusters[0].doc_ids == ["a", "b"] and clusters[0].corroboration == 2
    assert clusters[0].claim == ORIGINAL  # the shorter wording wins


def test_same_claim_from_same_doc_counts_once():
    clusters = deduplicate([Finding(claim=ORIGINAL, doc_id="a", subq="cost"),
                            Finding(claim=ORIGINAL, doc_id="a", subq="safety")])
    assert len(clusters) == 1 and clusters[0].corroboration == 1 and clusters[0].variants == 2
    assert clusters[0].subq == "cost"  # first section in plan order keeps it


# --- fetcher ---------------------------------------------------------------------------------

def make_docs(n, latency_ms=30, **extra):
    return {f"d{i}": Doc(id=f"d{i}", title="t", url=f"local://x/{i}", body="b", latency_ms=latency_ms, **extra)
            for i in range(n)}


def test_concurrency_is_bounded():
    async def go():
        fetcher = Fetcher(make_docs(8), max_concurrency=2)
        await asyncio.gather(*(fetcher.fetch(f"d{i}") for i in range(8)))
        return fetcher
    assert asyncio.run(go()).peak_concurrency == 2


def test_single_flight_shares_one_request_between_concurrent_callers():
    async def go():
        fetcher = Fetcher(make_docs(1))
        docs = await asyncio.gather(*(fetcher.fetch("d0") for _ in range(5)))
        return fetcher, docs
    fetcher, docs = asyncio.run(go())
    assert fetcher.network_calls == 1 and fetcher.deduplicated_requests == 4
    assert all(d.id == "d0" for d in docs)


def test_flaky_source_succeeds_on_retry():
    async def go():
        fetcher = Fetcher(make_docs(1, flaky=True), retries=1)
        return fetcher, await fetcher.fetch("d0")
    fetcher, doc = asyncio.run(go())
    assert doc.id == "d0" and fetcher.attempts["d0"] == 2


def test_slow_source_times_out_after_bounded_attempts():
    async def go():
        fetcher = Fetcher(make_docs(1, latency_ms=500), timeout_s=0.05, retries=2)
        with pytest.raises(TransientFetchError, match="3 attempts"):
            await fetcher.fetch("d0")
        return fetcher
    assert asyncio.run(go()).attempts["d0"] == 3


# --- end to end ------------------------------------------------------------------------------

def test_workers_run_in_parallel(run_demo):
    _, report = run_demo
    assert len(report.workers) == 4
    assert report.wall_ms < report.fetch_ms_total


def test_report_dedups_the_syndicated_copy_and_cites_both(run_demo):
    _, report = run_demo
    cost = report.sections["cost"]
    top = cost[0]
    assert set(top.doc_ids) == {"battery-basics", "battery-basics-syndicated"}
    assert report.raw_findings > sum(len(v) for v in report.sections.values())


def test_failed_source_is_reported_not_silently_dropped(run_demo):
    _, report = run_demo
    safety = next(w for w in report.workers if w.subq == "safety")
    assert "slow-blog" in safety.failed
    assert "## Not included" in render_markdown(report)


def test_every_citation_points_at_a_listed_source(run_demo):
    _, report = run_demo
    markdown = render_markdown(report)
    for i in range(1, len(report.sources) + 1):
        assert f"[{i}]" in markdown
    assert f"[{len(report.sources) + 1}]" not in markdown


class HallucinatingExtractor:
    name = "hallucinator"

    def complete(self, system, prompt):
        real = json.loads(MockExtractor().complete(system, prompt))["claims"]
        return json.dumps({"claims": real + ["Home batteries are free for everyone in 2026."]})


def test_ungrounded_claims_are_dropped():
    docs = load_corpus(CORPUS)
    swarm = Swarm(SearchIndex(docs), Fetcher(docs), MockPlanner(), HallucinatingExtractor())
    report = asyncio.run(swarm.run(QUESTION))
    claims = [c.claim for cs in report.sections.values() for c in cs]
    assert claims and not any("free for everyone" in c for c in claims)
    assert grounded(ORIGINAL, docs["battery-basics"]) and not grounded(ORIGINAL, docs["ev-charging"])


class BrokenPlanner:
    name = "broken"

    def complete(self, system, prompt):
        return "Sure! Here are some ideas: costs, safety, savings."


def test_invalid_plan_falls_back_to_one_worker():
    docs = load_corpus(CORPUS)
    swarm = Swarm(SearchIndex(docs), Fetcher(docs), BrokenPlanner(), MockExtractor())
    report = asyncio.run(swarm.run("home battery safety and fire risk"))
    assert [s.id for s in report.plan.subquestions] == ["main"]
    assert report.sections["main"]
