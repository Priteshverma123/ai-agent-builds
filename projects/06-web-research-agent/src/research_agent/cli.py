"""CLI: research one question over the local web and print the full trace plus a cited brief.

Used by `demo.py`, `python -m research_agent` and the `research-agent` console script.

    python demo.py
    python demo.py "How much do heat pumps cost to install?"
    python demo.py --max-fetches 2 "Are heat pumps worth it in cold climates?"
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .agent import Brief, ResearchAgent
from .config import Settings
from .corpus import LocalWeb
from .llm import make_llm
from .trace import Trace

DEFAULT_QUESTION = "Are heat pumps worth it in cold climates?"


def research(argv: list[str] | None = None) -> Brief:
    """Parse args, build the agent from settings, run it, and return the brief (tests use this)."""
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="A web research agent that writes cited briefs.")
    parser.add_argument("question", nargs="*", help=f"what to research (default: {DEFAULT_QUESTION!r})")
    parser.add_argument(
        "--web-dir", type=Path, default=settings.web_dir, help="local 'web' folder (env: RESEARCH_WEB_DIR)"
    )
    parser.add_argument(
        "--max-fetches", type=int, default=settings.max_fetches, help="fetch budget (env: RESEARCH_MAX_FETCHES)"
    )
    args = parser.parse_args(argv)

    settings = replace(settings, web_dir=args.web_dir, max_fetches=args.max_fetches)
    question = " ".join(args.question) or DEFAULT_QUESTION
    web = LocalWeb.from_dir(settings.web_dir)
    agent = ResearchAgent(web, make_llm(settings), config=settings.research_config(), trace=Trace())
    return agent.run(question)


def main(argv: list[str] | None = None) -> None:
    """Console entry point: returns None so the process exits with status 0."""
    research(argv)


if __name__ == "__main__":
    main()
