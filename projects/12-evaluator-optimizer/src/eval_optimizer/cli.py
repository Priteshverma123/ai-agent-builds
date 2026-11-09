"""Command-line entry: write a launch announcement, then let a rubric-driven critic push it to a target score.

    eval-optimizer                      # brief from examples/brief.json
    eval-optimizer --brief my_brief.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .llm import make_llm
from .optimizer import EvaluatorOptimizer
from .rubric import Brief, Rubric
from .trace import Trace


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Writer + rubric critic loop with scores and stop criteria.")
    parser.add_argument("--brief", type=Path, default=settings.brief_file, help="brief JSON (see examples/brief.json)")
    args = parser.parse_args(argv)

    brief = Brief.from_dict(json.loads(args.brief.read_text(encoding="utf-8")))
    llm = make_llm(settings)  # same model writes and judges here; see README for why you might split them
    optimizer = EvaluatorOptimizer(llm, Rubric(brief, judge=llm), target=settings.target,
                                   max_iterations=settings.max_iterations, patience=settings.patience,
                                   min_delta=settings.min_delta, fixes_per_round=settings.fixes_per_round,
                                   trace=Trace())
    optimizer.run(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
