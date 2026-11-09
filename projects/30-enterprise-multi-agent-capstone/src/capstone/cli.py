"""Command-line entry: ``capstone demo | evals | serve | mcp-stdio`` (used by demo.py and run_evals.py)."""
from __future__ import annotations

import argparse

from capstone.config import Settings


def run_evals(settings: Settings) -> int:
    """Print the eval report; exit code 1 if any case fails, so CI can gate merges on it."""
    from capstone.container import build
    from capstone.services.evals import load_cases, report, run_suite

    system = build(settings=settings)
    results = run_suite(lambda q: system.orchestrator.ask(q)[0], load_cases(settings.evals_path))
    print(report(results))
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Enterprise multi-agent assistant (AI Agent Builds #30)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="MCP discovery + five traced requests + eval summary")
    sub.add_parser("evals", help="full eval report; exit code 1 on any failure")
    serve = sub.add_parser("serve", help="run the FastAPI assistant with uvicorn")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)
    sub.add_parser("mcp-stdio", help="serve the tools over stdio (one JSON-RPC message per line)")
    args = parser.parse_args(argv)

    if args.command == "demo":
        from capstone.demo import main as demo

        demo(settings)
        return 0
    if args.command == "evals":
        return run_evals(settings)
    if args.command == "mcp-stdio":
        from capstone.adapters.mcp_stdio import main as stdio

        stdio()
        return 0
    import uvicorn

    uvicorn.run("capstone.serve:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
