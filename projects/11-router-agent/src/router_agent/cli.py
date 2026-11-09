"""Command-line entry: route customer messages, then evaluate the router on a labelled set.

    router-agent                                   # six sample messages + the eval report
    router-agent "Can I pay by bank transfer?"     # route your own messages (no eval)
"""

from __future__ import annotations

import argparse

from .agent import RouterAgent, evaluate, load_labelled, print_report
from .config import Settings
from .llm import make_llm
from .router import Router
from .specialists import BillingAgent, SalesAgent, TechSupportAgent
from .trace import Trace

MESSAGES = [
    "I was charged twice on invoice INV-1042",
    "My app keeps crashing when I upload a photo",
    "Do you offer discounts for teams of 50 people?",
    "How do I export my data to CSV?",
    "I can't log in and I also want a refund",
    "What's the weather in Paris?",
]


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Rules + LLM intent router with confidence threshold and fallback.")
    parser.add_argument("messages", nargs="*", help="messages to route (default: six samples, then the eval report)")
    args = parser.parse_args(argv)

    trace = Trace()
    router = Router.from_file(make_llm(settings), settings.intents_file, threshold=settings.threshold)
    agent = RouterAgent(router, [BillingAgent(), TechSupportAgent(), SalesAgent()], trace=trace)
    trace.box("ROUTER AGENT", [f"model: {router.llm.name} | threshold: {router.threshold} | "
                               f"specialists: {', '.join(agent.specialists)} + fallback"])
    for message in args.messages or MESSAGES:
        agent.handle(message)
    if not args.messages:
        print_report(evaluate(router, load_labelled(settings.labelled_file)), trace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
