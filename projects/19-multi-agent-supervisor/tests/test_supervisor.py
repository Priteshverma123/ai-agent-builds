"""The supervisor routes in the right order, merges parallel work, and never trusts a bad decision."""

import asyncio
import json
from pathlib import Path

from supervisor.cli import GOAL, build_team
from supervisor.llm import MockSupervisorLLM
from supervisor.messages import WorkerResult
from supervisor.supervisor import Limits, Supervisor
from supervisor.trace import Tracer
from supervisor.workers import Coder, KnowledgeBase, Researcher, Reviewer

KB = Path(__file__).resolve().parents[1] / "examples" / "kb"


def run(supervisor: Supervisor):
    return asyncio.run(supervisor.run(GOAL))


class ScriptedLLM:
    """Replies with a fixed sequence of strings, then repeats the last one."""

    name = "scripted"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    def complete(self, system, prompt):
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


class NaiveCoderLLM:
    """Never learns from feedback - the supervisor must stop it."""

    name = "naive"

    def complete(self, system, prompt):
        return '```python\ndef slugify(title):\n    """Slug."""\n    return title.lower()\n```'


def team(llm, coder_llm=None, tracer=None, limits=None):
    from supervisor.llm import MockCoderLLM

    workers = [Researcher(KnowledgeBase(KB), latency_s=0.0), Coder(coder_llm or MockCoderLLM()), Reviewer()]
    return Supervisor(workers, llm, limits, tracer or Tracer())


def test_routes_research_code_review_fix_review_then_finishes():
    tracer = Tracer()
    result = run(build_team(tracer=tracer))
    assert [e.worker for e in result.ledger] == ["researcher", "researcher", "coder", "reviewer", "coder", "reviewer"]
    assert result.status == "approved" and result.version == 2 and result.steps == 5
    assert "FALLBACK" not in tracer.steps()


def test_merges_parallel_research_into_one_set_of_notes():
    result = run(build_team())
    assert result.sources == ["url-style-guide", "slug-examples"]
    assert len(result.rules) == 5 and result.checks == 6


def test_parallel_safe_workers_really_run_concurrently():
    in_flight, peak = 0, 0

    class ProbeResearcher(Researcher):
        async def run(self, instruction, state):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1
            return await super().run(instruction, state)

    sup = Supervisor([ProbeResearcher(KnowledgeBase(KB), latency_s=0.0), Coder(NaiveCoderLLM()), Reviewer()],
                     MockSupervisorLLM(), Limits(max_steps=1))
    run(sup)
    assert peak == 2


def test_garbage_model_output_falls_back_to_rules_and_still_ships():
    tracer = Tracer()
    result = run(team(ScriptedLLM("I think the coder should go next, probably?"), tracer=tracer))
    assert result.status == "approved"
    assert tracer.steps().count("FALLBACK") >= 5


def test_unknown_worker_and_parallel_coders_are_rejected():
    tracer = Tracer()
    bad = [
        json.dumps({"next": [{"worker": "deployer", "instruction": "ship it to prod"}], "reason": "yolo"}),
        json.dumps({"next": [{"worker": "coder", "instruction": "write a"}, {"worker": "coder", "instruction": "write b"}],
                    "reason": "faster"}),
    ]
    sup = team(ScriptedLLM(*bad), tracer=tracer, limits=Limits(max_steps=2))
    asyncio.run(sup.run(GOAL))
    fallbacks = [e.lines[0] for e in tracer.events if e.step == "FALLBACK"]
    assert any("deployer" in line for line in fallbacks)
    assert any("not parallel-safe" in line for line in fallbacks)


def test_premature_finish_is_not_approved():
    result = run(team(ScriptedLLM(json.dumps({"next": "FINISH", "reason": "looks done to me"}))))
    assert result.status == "incomplete" and result.code is None


def test_visit_budget_stops_a_coder_that_never_improves():
    result = run(team(MockSupervisorLLM(), coder_llm=NaiveCoderLLM(), limits=Limits(max_steps=20)))
    assert result.status == "incomplete"
    assert result.reason == "coder visit budget exhausted"
    assert [e.worker for e in result.ledger].count("coder") == 3


def test_ledger_attributes_every_change():
    result = run(build_team())
    assert all(isinstance(e.step, int) and e.worker and e.instruction for e in result.ledger)
    assert result.ledger[3].summary.startswith("v1 FAILED")


def test_worker_results_are_typed():
    r = WorkerResult(worker="coder", instruction="x", summary="y")
    assert r.ok and r.code is None
