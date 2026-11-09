"""RouterAgent ties the router to the specialists, and ``evaluate`` measures the router.

A router is a classifier, so treat it like one: keep a labelled set of real messages
(including ones that *should* hit the fallback) and check accuracy on every change.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .router import FALLBACK, RouteDecision, Router
from .specialists import FallbackAgent, Specialist
from .trace import Trace


@dataclass
class Response:
    decision: RouteDecision
    agent: str
    reply: str


class RouterAgent:
    def __init__(self, router: Router, specialists: list[Specialist], trace: Trace | None = None) -> None:
        self.router = router
        self.specialists = {s.name: s for s in specialists}
        missing = set(router.intents) - set(self.specialists)
        if missing:
            raise ValueError(f"no specialist for intents: {sorted(missing)}")
        self.fallback = FallbackAgent([s.name.replace("_", " ") for s in specialists])
        self.trace = trace or Trace(echo=False)

    def handle(self, message: str) -> Response:
        decision = self.router.route(message)
        if decision.intent == FALLBACK:
            reply = self.fallback.handle(message, [c.replace("_", " ") for c in decision.candidates])
        else:
            reply = self.specialists[decision.intent].handle(message)
        self.trace.event("user", message)
        self.trace.event("route", f"{decision.intent:<13} conf {decision.confidence:4.2f}  via {decision.method:<8}",
                         [decision.reason])
        self.trace.event("reply", f"({decision.intent}) {reply}")
        self.trace.blank()
        return Response(decision, decision.intent, reply)


@dataclass
class EvalReport:
    rows: list[tuple[str, str, RouteDecision]]  # (message, expected, decision)

    @property
    def correct(self) -> int:
        return sum(expected == d.intent for _, expected, d in self.rows)

    @property
    def accuracy(self) -> float:
        return self.correct / len(self.rows) if self.rows else 0.0

    def methods(self) -> Counter:
        return Counter(d.method for _, _, d in self.rows)

    def mistakes(self) -> list[tuple[str, str, str]]:
        return [(m, expected, d.intent) for m, expected, d in self.rows if expected != d.intent]


def load_labelled(path: str | Path) -> list[tuple[str, str]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [(row["message"], row["intent"]) for row in map(json.loads, filter(str.strip, lines))]


def evaluate(router: Router, labelled: list[tuple[str, str]]) -> EvalReport:
    return EvalReport([(message, expected, router.route(message)) for message, expected in labelled])


def print_report(report: EvalReport, trace: Trace) -> None:
    rows = [f"{'ok':<3} {'expected':<13} {'routed':<13} {'conf':>4}  {'via':<8} message"]
    for message, expected, d in report.rows:
        mark = "ok" if expected == d.intent else "XX"
        shown = message if len(message) <= 38 else message[:35] + "..."
        rows.append(f"{mark:<3} {expected:<13} {d.intent:<13} {d.confidence:4.2f}  {d.method:<8} {shown}")
    methods = ", ".join(f"{k} {v}" for k, v in sorted(report.methods().items()))
    trace.box(f"ROUTER EVAL  accuracy {report.correct}/{len(report.rows)} = {report.accuracy:.0%}   ({methods})", rows)
