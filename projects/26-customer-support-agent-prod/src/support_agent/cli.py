"""Command-line entry: ``support-agent demo | evals | serve`` (also used by run.py and demo.py)."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Customer support agent (AI Agent Builds #26)")
    parser.add_argument("command", choices=["demo", "evals", "serve"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "demo":
        from .demo import main as demo

        demo()
        return 0
    if args.command == "evals":
        from .config import Settings
        from .evals import DEMO_TODAY, format_report, run_suite

        results = run_suite(Settings(today=DEMO_TODAY, log_level="WARNING"))
        print(format_report(results))
        return 0 if all(r.passed for r in results) else 1
    import uvicorn

    uvicorn.run("support_agent.api:create_app", factory=True, host="127.0.0.1", port=args.port)
    return 0
