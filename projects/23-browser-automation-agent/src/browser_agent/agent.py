"""The observe -> act loop: show the model the snapshot, run the action it picks, show it the new snapshot."""

from __future__ import annotations

import re

from .browser import Browser
from .llm import LLM, ToolResult
from .tools import TOOLS, execute
from .trace import Trace

SYSTEM = """You operate a web browser to complete the user's goal.
You see the page as an accessibility snapshot: one line per element, "- role "name" [props] [ref=eN]: value".
Act only on refs from the LATEST snapshot; refs from older pages are invalid after navigation.
Every action returns OK/ERROR plus the new snapshot. Read errors and alerts and fix the problem.
Before accepting a confirmation dialog, check that it matches what the user asked for.
Never enter data the user did not give you. Call finish when the goal is done or impossible."""


def describe(ref: str, snapshot: str) -> str:
    """Find ``role "name"`` for a ref in the snapshot, for a readable trace."""
    match = re.search(rf'- (\w+)(?: "([^"]*)")?[^\n]*\[ref={ref}\]', snapshot)
    return f'{match.group(1)} "{match.group(2) or ""}"' if match else "?"


class BrowserAgent:
    def __init__(self, browser: Browser, llm: LLM, max_steps: int = 25, trace: Trace | None = None,
                 show_snapshots: bool = False) -> None:
        self.browser = browser
        self.llm = llm
        self.max_steps = max_steps
        self.trace = trace or Trace(quiet=True)
        self.show_snapshots = show_snapshots

    def run(self, goal: str, start_url: str = "/index.html") -> str:
        first = self.browser.navigate(start_url)
        self.trace.row("goal", goal)
        self.trace.snapshot(first.snapshot)
        self.llm.start(SYSTEM, f"Goal: {goal}\n\nCurrent page:\n{first.snapshot}", TOOLS)
        snapshot, results = first.snapshot, []
        for step in range(1, self.max_steps + 1):
            turn = self.llm.next_turn(results)
            if turn.thought:
                self.trace.row("think", f"(step {step}) {turn.thought}")
            if not turn.tool_calls:
                return self._done(turn.answer or "")
            results = []
            for call in turn.tool_calls:
                if call.name == "finish":
                    return self._done(call.arguments.get("answer", ""))
                args = {k: v for k, v in call.arguments.items() if k not in ("ref", "element")}
                target = f"{call.arguments['ref']} ({describe(call.arguments['ref'], snapshot)})" if "ref" in call.arguments else ""
                self.trace.row("act", f"{call.name} {target} {args if args else ''}".strip())
                result = execute(self.browser, call.name, call.arguments)
                snapshot = result.snapshot
                self.trace.row("ok" if result.ok else "error", result.message)
                self.trace.row("page", f"{snapshot.splitlines()[0][6:]}  [{snapshot.count('[ref=')} refs]")
                if self.show_snapshots:
                    self.trace.snapshot(snapshot)
                results.append(ToolResult(call.id, call.name, result.for_model(), not result.ok))
        return self._done(f"Stopped after {self.max_steps} steps without finishing.")

    def _done(self, answer: str) -> str:
        self.trace.row("answer", answer)
        return answer
