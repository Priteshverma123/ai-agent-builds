"""Command line.

    python demo.py                                         # review examples/change.diff
    python demo.py --diff my.diff --base path/to/repo      # review your own change
    git diff | python demo.py --diff - --base .            # straight from git
    python demo.py --format markdown > review.md           # PR comment
    python demo.py --fail-on high                          # CI: exit 1 if any HIGH+ finding
    python demo.py --static-only                           # skip the LLM pass
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import ReviewAgent
from .config import load_settings
from .findings import Severity
from .llm import MockReviewerLLM, llm_from_env
from .render import as_json, markdown, terminal

def main(argv: list[str] | None = None) -> None:
    settings = load_settings()  # env defaults (REVIEW_*); flags below override them
    parser = argparse.ArgumentParser(description="Diff-aware code review agent")
    parser.add_argument("--diff", default=settings.diff, help="unified diff file or -")
    parser.add_argument("--base", type=Path, default=settings.base, help="repo checkout before the change")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default=settings.output_format)
    parser.add_argument("--fail-on", choices=[s.name.lower() for s in Severity], default=settings.fail_on,
                        help="exit 1 at this severity")
    parser.add_argument("--static-only", action="store_true", default=settings.static_only)
    args = parser.parse_args(argv)

    diff_text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    agent = ReviewAgent(None if args.static_only else llm_from_env(MockReviewerLLM()))
    result = agent.review(diff_text, args.base)
    print({"text": terminal, "markdown": markdown, "json": as_json}[args.format](result))

    if args.fail_on:
        threshold = Severity[args.fail_on.upper()]
        sys.exit(1 if any(f.severity >= threshold for f in result.findings) else 0)
