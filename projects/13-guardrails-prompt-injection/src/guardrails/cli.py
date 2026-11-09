"""Command-line entry point, used by `python demo.py`, `python -m guardrails` and `guardrails-demo`."""

from __future__ import annotations

import argparse

from .demo import SCENARIOS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt-injection guardrails demo")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="run one scenario (default: all)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    for key in [args.scenario] if args.scenario else sorted(SCENARIOS):
        SCENARIOS[key]()
