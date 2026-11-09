"""Demo: two debates - one reaches consensus (with dissent kept), one honestly doesn't."""

from __future__ import annotations

import argparse
import asyncio
import json

from .config import load_settings
from .debate import Debate, stances
from .debater import make_panel
from .llm import MockDebateLLM, llm_from_env
from .messages import Position
from .render import box, render_round, render_verdict


def printer():
    """Print each round as it finishes, remembering stances so shifts can be highlighted."""
    previous: dict[str, str] = {}

    def on_round(round_no: int, positions: list[Position], stable: bool) -> None:
        print(render_round(round_no, positions, previous, stable))
        previous.update({k: v for k, v in stances(positions).items() if v})

    return on_round


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Multi-agent debate with a judge that surfaces disagreement")
    parser.add_argument("question", nargs="*", help="debate your own question (needs a real LLM)")
    parser.add_argument("--max-rounds", type=int, default=settings.max_rounds)
    args = parser.parse_args(argv)

    script = settings.script_path
    llm = llm_from_env(MockDebateLLM(script), settings)
    questions = [" ".join(args.question)] if args.question else \
        [q["text"] for q in json.loads(script.read_text(encoding="utf-8"))["questions"].values()]
    for question in questions:
        panel = make_panel(llm)
        print(box("DEBATE", [question, f"panel: {', '.join(d.name for d in panel)}   model: {llm.name}"]))
        verdict = asyncio.run(Debate(panel, max_rounds=args.max_rounds, threshold=settings.threshold,
                                     on_round=printer()).run(question))
        print(render_verdict(verdict))
        print()
    return 0
