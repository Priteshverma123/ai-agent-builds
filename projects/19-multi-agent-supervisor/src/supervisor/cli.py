"""Demo: a supervisor ships a slugify() function with a researcher, a coder and a reviewer."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import Settings, load_settings
from .llm import MockCoderLLM, MockSupervisorLLM, llm_from_env
from .supervisor import Deliverable, Limits, Supervisor
from .trace import Tracer, box
from .workers import Coder, KnowledgeBase, Researcher, Reviewer

GOAL = "Write a Python function slugify(title) that follows our URL style guide."


def build_team(kb_dir: Path | None = None, tracer: Tracer | None = None,
               limits: Limits | None = None, settings: Settings | None = None) -> Supervisor:
    """Wire the three workers and the supervisor from settings (env) plus any explicit overrides."""
    settings = settings or load_settings()
    limits = limits or Limits(max_steps=settings.max_steps,
                              max_visits={"coder": settings.max_coder_visits})
    workers = [Researcher(KnowledgeBase(kb_dir or settings.kb_dir)),
               Coder(llm_from_env(MockCoderLLM(), settings)),
               Reviewer(timeout_s=settings.review_timeout_s)]
    return Supervisor(workers, llm_from_env(MockSupervisorLLM(), settings), limits, tracer)


def render(result: Deliverable) -> str:
    ledger = [f"{e.step:>2}  {e.worker:<10}  {e.summary}" for e in result.ledger]
    lines = [
        f"status : {result.status.upper()}   ({result.reason})",
        f"steps  : {result.steps}   sources: {', '.join(result.sources) or '-'}",
        f"checks : {result.checks} passed on v{result.version}" if result.status == "approved"
        else f"checks : last review did not pass on v{result.version}",
        "",
        "--- final code ---",
        *(result.code or "(none)").rstrip().splitlines(),
        "",
        "--- who did what ---",
        *ledger,
    ]
    return box("DELIVERABLE", lines)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Supervisor delegating to researcher / coder / reviewer")
    parser.add_argument("--max-steps", type=int, default=settings.max_steps)
    args = parser.parse_args(argv)

    limits = Limits(max_steps=args.max_steps, max_visits={"coder": settings.max_coder_visits})
    supervisor = build_team(tracer=Tracer(echo=True), limits=limits, settings=settings)
    print(box("MULTI-AGENT SUPERVISOR", [
        f"goal   : {GOAL}",
        f"model  : {supervisor.llm.name}",
        "workers: " + ", ".join(supervisor.workers),
    ]))
    result = asyncio.run(supervisor.run(GOAL))
    print(render(result))
    return 0 if result.status == "approved" else 1
