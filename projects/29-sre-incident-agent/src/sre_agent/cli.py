"""Command-line entry used by `demo.py` and the `sre-agent` script."""
from __future__ import annotations

import argparse

from sre_agent.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SRE incident agent (AI Agent Builds #29): triage ALERT-5521")
    parser.add_argument("--interactive", action="store_true",
                        help="you are the on-call: approve or deny each mutating step at the terminal")
    args = parser.parse_args(argv)

    from sre_agent.demo import main as demo

    demo(interactive=args.interactive, settings=Settings.from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
