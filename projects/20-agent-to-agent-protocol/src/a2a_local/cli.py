"""Command line entry: run the three-agent demo, or serve one specialist agent on a real port.

    python demo.py ["<your trip request>"]
    python -m a2a_local --serve fx --port 8001
"""

from __future__ import annotations

import argparse
import dataclasses
from collections.abc import Callable

from fastapi import FastAPI

from .agents import build_currency_agent, build_weather_agent
from .client import A2AClient
from .config import Settings, load_settings
from .llm import make_llm
from .planner import Planner
from .serve import LocalAgentServer
from .trace import Trace

REQUEST = ("I live in Toronto and I'm flying to Tokyo in April with 500 dollars. "
           "What is that in yen, and what should I pack?")


def agent_builders(settings: Settings) -> dict[str, Callable[[str], FastAPI]]:
    """The specialist agents this project can serve, by short name."""
    return {"fx": build_currency_agent,
            "weather": lambda url: build_weather_agent(url, work_seconds=settings.weather_work_seconds)}


def run_demo(request: str, settings: Settings) -> str:
    """Start both agents on free ports, then let the planner discover them and delegate."""
    trace = Trace()
    builders = agent_builders(settings)
    with LocalAgentServer(builders["fx"]) as fx, LocalAgentServer(builders["weather"]) as weather:
        trace.box("0. TWO REMOTE AGENTS ARE RUNNING (separate HTTP servers)", [
            f"FX Desk          {fx.url}   (instant)",
            f"Packing Weather  {weather.url}   (slow: ~{settings.weather_work_seconds} s per task)"])
        remotes = [A2AClient(fx.url, on_wire=trace.wire("FX Desk")),
                   A2AClient(weather.url, on_wire=trace.wire("Weather"))]
        llm = make_llm(settings)
        planner = Planner(remotes, llm, trace, max_followups=settings.max_followups)

        trace.box("1. DISCOVERY  (read each agent card; no agent is hard-coded in the planner)")
        planner.discover()

        trace.box(f"2. PLAN + DELEGATE + FOLLOW UP  (planner model: {llm.name})")
        answer = planner.run(request)

        trace.box("3. WHAT THE PROTOCOL GUARANTEES", [
            "- Every delegation is a Task with an id, a contextId and a state machine:",
            "  submitted -> working -> (input-required -> working) -> completed | failed | canceled",
            "- Follow-up answers go to the SAME task id, so the remote agent keeps its context.",
            "- Non-blocking sends + tasks/get polling let slow agents work in parallel."])
    return answer


def serve(name: str, settings: Settings) -> None:
    """Run one specialist agent in the foreground (Ctrl+C to stop)."""
    import uvicorn

    url = f"http://{settings.host}:{settings.port}"
    print(f"Serving '{name}' at {url}  (card: {url}/.well-known/agent-card.json)")
    uvicorn.run(agent_builders(settings)[name](url), host=settings.host, port=settings.port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="A2A-style agent-to-agent delegation over local HTTP")
    parser.add_argument("request", nargs="?", default=REQUEST, help="the trip request for the planner")
    parser.add_argument("--serve", choices=["fx", "weather"], help="serve one specialist agent instead of the demo")
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args(argv)
    if args.serve:
        serve(args.serve, dataclasses.replace(settings, port=args.port))
        return 0
    run_demo(args.request, settings)
    return 0
