"""Command-line entry: ``gateway demo`` (teaching trace) or ``gateway serve`` (real HTTP server)."""
from __future__ import annotations

import argparse

from gateway.config import Settings


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Multi-tenant agent gateway (AI Agent Builds #28)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="nine scenes through the gateway with MockLLM and a fake clock")
    serve = sub.add_parser("serve", help="run the FastAPI gateway with uvicorn")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args(argv)

    if args.command == "demo":
        from gateway.demo import main as demo

        demo()
        return 0
    import uvicorn

    uvicorn.run("gateway.serve:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
