"""Debate behaviour: consensus with dissent, honest no-consensus, robustness, independence, parallelism."""

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from debate.debate import Debate
from debate.debater import Debater, make_panel
from debate.judge import judge
from debate.llm import MockDebateLLM
from debate.messages import Argument, Position

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "debates.json"
QUESTIONS = {k: v["text"] for k, v in json.loads(SCRIPT.read_text(encoding="utf-8"))["questions"].items()}


def run(question, debaters=None, **kwargs):
    return asyncio.run(Debate(debaters or make_panel(MockDebateLLM(SCRIPT)), **kwargs).run(question))


def pos(agent, stance, confidence, *claims, rnd=1, because=""):
    return Position(agent=agent, round=rnd, argument=Argument(
        stance=stance, confidence=confidence, claims=list(claims) or ["x: y"], changed_because=because))


def test_consensus_is_reached_and_the_minority_is_kept():
    v = run(QUESTIONS["microservices"])
    assert v.consensus and v.decision == "against"
    assert v.agreement == pytest.approx(2.2 / 2.8, abs=1e-3)
    assert len(v.dissent) == 1 and v.dissent[0].startswith("architect (conditional")
    assert [c.topic for c in v.cruxes] == ["velocity"]


def test_debate_stops_early_once_stances_settle():
    assert run(QUESTIONS["microservices"], max_rounds=6).rounds == 3


def test_split_debate_reports_no_consensus_and_shows_every_side():
    v = run(QUESTIONS["automerge"])
    assert not v.consensus and v.decision == "no consensus"
    assert len(v.dissent) == 4
    assert {c.topic for c in v.cruxes} == {"security", "toil"}


def test_unexplained_stance_change_is_flagged():
    v = run(QUESTIONS["automerge"])
    flagged = [s for s in v.shifts if s.unexplained]
    assert [(s.agent, s.before, s.after) for s in flagged] == [("pm", "for", "conditional")]
    explained = run(QUESTIONS["microservices"]).shifts
    assert len(explained) == 1 and not explained[0].unexplained


def test_judge_weights_by_confidence_and_respects_threshold():
    rounds = [[pos("a", "for", 0.9), pos("b", "for", 0.5), pos("c", "against", 0.6)]]
    v = judge("q", rounds, threshold=0.66)
    assert v.tally == {"for": 1.4, "against": 0.6} and v.agreement == 0.7 and v.consensus
    assert not judge("q", rounds, threshold=0.75).consensus


def test_crux_needs_two_agents_on_two_sides():
    rounds = [[pos("a", "for", 0.9, "cost: cheap"), pos("b", "against", 0.5, "cost: pricey", "ops: hard")]]
    rounds.append([pos("a", "conditional", 0.9, "ops: fine", rnd=2, because="b"), pos("b", "against", 0.5, "ops: hard", rnd=2)])
    assert {c.topic for c in judge("q", rounds).cruxes} == {"cost", "ops"}
    solo = [[pos("a", "for", 0.9, "cost: x")], [pos("a", "against", 0.9, "cost: y", rnd=2, because="z")]]
    assert judge("q", solo).cruxes == []


class FlakyLLM:
    """Garbage for one agent, valid JSON for everyone else."""

    name = "flaky"

    def __init__(self, bad_agent, recover_after=None):
        self.bad_agent, self.recover_after, self.calls = bad_agent, recover_after, 0

    def complete(self, system, prompt):
        if f"AGENT: {self.bad_agent}" in prompt:
            self.calls += 1
            if self.recover_after is None or self.calls <= self.recover_after:
                return "As an AI, I think both sides have merit."
        return json.dumps({"stance": "for", "confidence": 0.7, "claims": ["speed: faster"]})


def test_invalid_replies_get_one_retry_then_abstain_and_do_not_vote():
    llm = FlakyLLM("sre")
    v = run("q", [Debater("sre", "p", llm), Debater("pm", "p", llm)], max_rounds=2)
    assert v.abstained == ["sre"] and v.tally == {"for": 0.7}
    assert llm.calls == 4  # 2 rounds x (first try + 1 retry)


def test_a_corrective_retry_can_recover():
    llm = FlakyLLM("sre", recover_after=1)
    p = asyncio.run(Debater("sre", "p", llm).argue("q", 1, ""))
    assert not p.abstained and llm.calls == 2


class SpyLLM:
    name = "spy"

    def __init__(self):
        self.prompts = []
        self.lock = threading.Lock()

    def complete(self, system, prompt):
        with self.lock:
            self.prompts.append(prompt)
        agent = prompt.split("AGENT: ")[1].split("\n")[0]
        return json.dumps({"stance": "for", "confidence": 0.5, "claims": [f"view: {agent} thinks so"]})


def test_openings_are_independent_and_rebuttals_see_only_others():
    spy = SpyLLM()
    asyncio.run(Debate([Debater("a", "p", spy), Debater("b", "p", spy)], max_rounds=2).run("q"))
    round1 = [p for p in spy.prompts if "ROUND: 1" in p]
    round2_a = next(p for p in spy.prompts if "ROUND: 2" in p and "AGENT: a" in p)
    assert all("WHAT THE OTHERS SAID" not in p for p in round1)
    assert "b thinks so" in round2_a and "a thinks so" not in round2_a


def test_debaters_in_a_round_run_in_parallel():
    class SlowLLM(SpyLLM):
        def complete(self, system, prompt):
            time.sleep(0.2)
            return super().complete(system, prompt)

    panel = [Debater(n, "p", SlowLLM()) for n in ("a", "b", "c", "d")]
    start = time.perf_counter()
    asyncio.run(Debate(panel, max_rounds=1).run("q"))
    assert time.perf_counter() - start < 0.6  # sequential would be 0.8 s


def test_argument_contract():
    with pytest.raises(ValidationError):
        Argument(stance="for", confidence=1.5, claims=["a: b"])
    with pytest.raises(ValidationError):
        Argument(stance="for", confidence=0.5, claims=["no topic here"])
    with pytest.raises(ValidationError):
        Argument(stance="maybe", confidence=0.5, claims=["a: b"])
