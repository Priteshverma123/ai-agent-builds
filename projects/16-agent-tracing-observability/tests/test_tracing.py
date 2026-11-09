import json
import re

import pytest

from tracekit.agent import Agent
from tracekit.exporters import JSONLExporter, read_jsonl, summarise
from tracekit.instrument import TracedLLM, TracedTools
from tracekit.llm import MockLLM
from tracekit.spans import SimClock, Tracer
from tracekit.viewer_html import render_html
from tracekit.viewer_terminal import render_trace

WEATHER = "What's the weather in Paris, and what is an 18% tip on a 42.50 bill?"
NEWS = "Find the latest news about solar batteries."


class CountingTools(TracedTools):
    """Counts real invocations underneath the tracing, so we can compare with the spans."""

    def __init__(self, tracer, clock):
        super().__init__(tracer, clock)
        self.invocations = 0
        for name, fn in list(self.handlers.items()):
            self.handlers[name] = self._count(fn)

    def _count(self, fn):
        def inner(**kwargs):
            self.invocations += 1
            return fn(**kwargs)
        return inner


@pytest.fixture
def traced(tmp_path):
    clock = SimClock()
    tracer = Tracer(clock, exporters=[JSONLExporter(tmp_path / "trace.jsonl")], deterministic_ids=True)
    llm, tools = MockLLM(clock), CountingTools(tracer, clock)
    return Agent(TracedLLM(llm, tracer), tools, tracer), tracer, llm, tools, tmp_path / "trace.jsonl"


def test_every_model_and_tool_call_is_captured(traced):
    agent, tracer, llm, tools, _ = traced
    agent.run(WEATHER)
    agent.run(NEWS)
    spans = tracer.finished
    assert sum(s.kind == "llm" for s in spans) == llm.calls == 5
    assert sum(s.kind == "tool" for s in spans) == tools.invocations == 4  # includes the failed search


def test_spans_form_one_tree_per_run(traced):
    agent, tracer, *_ = traced
    agent.run(WEATHER)
    spans = tracer.finished
    ids = {s.span_id for s in spans}
    roots = [s for s in spans if s.parent_id is None]
    assert len(roots) == 1 and roots[0].kind == "agent"
    assert {s.trace_id for s in spans} == {roots[0].trace_id}
    assert all(s.parent_id in ids for s in spans if s.parent_id)
    by_id = {s.span_id: s for s in spans}
    assert all(by_id[s.parent_id].kind == "step" for s in spans if s.kind in ("llm", "tool"))
    for s in spans:  # children sit inside their parent's time window
        if s.parent_id:
            parent = by_id[s.parent_id]
            assert parent.start_ms <= s.start_ms and s.end_ms <= parent.end_ms


def test_failures_are_recorded_and_the_retry_is_visible(traced):
    agent, tracer, *_ = traced
    answer = agent.run(NEWS)
    failed = [s for s in tracer.finished if s.status == "error"]
    assert len(failed) == 1 and failed[0].name == "tool search"
    assert failed[0].events[0]["type"] == "TimeoutError" and failed[0].duration_ms == 1500
    step = next(s for s in tracer.finished if s.name == "step 1")
    assert step.events[0]["name"] == "retry"
    assert "sodium" in answer


def test_tokens_and_cost_are_attributed(traced):
    agent, tracer, *_ = traced
    agent.run(WEATHER)
    summary = summarise(tracer.finished)
    assert summary.llm_calls == 3 and summary.input_tokens > 0 and summary.output_tokens > 0
    expected = (summary.input_tokens * 4 + summary.output_tokens * 20) / 1e6
    assert summary.cost_usd == pytest.approx(expected, abs=1e-5)


def test_jsonl_export_round_trips(traced):
    agent, tracer, _, _, path = traced
    agent.run(WEATHER)
    loaded = read_jsonl(path)
    assert [s.to_dict() for s in loaded] == [s.to_dict() for s in tracer.finished]
    assert render_trace(loaded) == render_trace(tracer.finished)


def test_secrets_never_reach_the_trace(traced):
    agent, tracer, _, _, path = traced
    agent.run("Find the latest news about sk-ABCDEFGHIJKLMNOPQRSTUV leaks")
    text = path.read_text()
    assert "sk-ABCDEFGHIJ" not in text and "[REDACTED]" in text


def test_exception_inside_a_span_still_closes_it():
    clock = SimClock()
    tracer = Tracer(clock)
    with pytest.raises(ValueError):
        with tracer.span("outer"):
            with tracer.span("inner"):
                clock.sleep(5)
                raise ValueError("boom")
    assert [s.status for s in tracer.finished] == ["error", "error"]
    assert all(s.end_ms == 5 for s in tracer.finished)
    assert tracer.current is None


def test_html_viewer_is_self_contained_and_escapes_hostile_text(traced):
    agent, tracer, *_ = traced
    agent.run(WEATHER)
    agent.run("Find the latest news about </script><script>alert(1)</script>")
    page = render_html(tracer.finished)
    assert not re.search(r"""(src|href)=["']?https?:""", page)
    assert page.count("</script>") == 2  # only our own two closing tags
    data = re.search(r'<script type="application/json" id="trace-data">(.*?)</script>', page, re.S).group(1)
    traces = json.loads(data)
    assert {s["span_id"] for t in traces for s in t["spans"]} == {s.span_id for s in tracer.finished}
