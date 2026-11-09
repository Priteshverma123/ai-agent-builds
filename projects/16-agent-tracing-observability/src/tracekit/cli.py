"""Command line: run the agent on a few questions, export JSONL + HTML, print the terminal waterfall.

    python demo.py                         # trace every question in examples/questions.txt
    python demo.py --real-clock            # wall-clock timings instead of simulated ones
    python demo.py --view out/trace.jsonl  # only render an existing trace
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .agent import Agent
from .config import load_settings
from .exporters import JSONLExporter, group_traces, read_jsonl
from .instrument import TracedLLM, TracedTools
from .llm import MockLLM, llm_from_env
from .spans import RealClock, SimClock, Tracer
from .viewer_html import write_html
from .viewer_terminal import render_trace



def run_demo(out_dir: Path, questions: list[str], real_clock: bool = False) -> tuple[Path, Path]:
    jsonl = out_dir / "trace.jsonl"
    llm = llm_from_env(MockLLM())
    use_sim = not real_clock and isinstance(llm, MockLLM)
    clock = SimClock() if use_sim else RealClock()
    if isinstance(llm, MockLLM):
        llm.clock = clock
    tracer = Tracer(clock, exporters=[JSONLExporter(jsonl)], deterministic_ids=use_sim)
    settings = load_settings()
    agent = Agent(TracedLLM(llm, tracer), TracedTools(tracer, clock), tracer,
                  max_steps=settings.max_steps, retries=settings.tool_retries)
    for question in questions:
        answer = agent.run(question)
        print(f"Q: {question}\nA: {answer}\n")
    return jsonl, write_html(tracer.finished, out_dir / "trace.html")


def main(argv: list[str] | None = None) -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Agent tracing demo")
    parser.add_argument("--out", type=Path, default=settings.out_dir)
    parser.add_argument("--questions", type=Path, default=settings.questions, help="one question per line")
    parser.add_argument("--real-clock", action="store_true", default=settings.real_clock,
                        help="measure wall time instead of simulated time")
    parser.add_argument("--view", type=Path, help="only render an existing trace.jsonl")
    args = parser.parse_args(argv)

    if args.view:
        spans = read_jsonl(args.view)
        html = write_html(spans, args.view.with_suffix(".html"))
    else:
        questions = [q for q in args.questions.read_text(encoding="utf-8").splitlines() if q.strip()]
        jsonl, html = run_demo(args.out, questions, args.real_clock)
        spans = read_jsonl(jsonl)  # render from the export, proving it holds everything
    for trace in group_traces(spans).values():
        print(render_trace(trace))
        print()
    print(f"{len(spans)} spans exported | HTML viewer: {os.path.relpath(html)}")
