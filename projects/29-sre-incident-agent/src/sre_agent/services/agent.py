"""The incident agent loop: think -> act (through the registry) -> observe -> update state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sre_agent.adapters.approval import Approver
from sre_agent.adapters.clock import SimClock
from sre_agent.adapters.infra import MockInfra
from sre_agent.adapters.llm import LLM
from sre_agent.adapters.telemetry import FileTelemetry
from sre_agent.domain.models import Action, ActionRecord, Alert, Hypothesis
from sre_agent.domain.state import AgentState
from sre_agent.services.tools import ToolResult, build_toolbox

EventHook = Callable[[str, dict[str, Any]], None]


def load_runbook(runbooks: dict[str, Any], h: Hypothesis) -> tuple[str, list[Action]]:
    """Fill a runbook's {placeholders} with the hypothesis parameters."""
    book = runbooks.get(h.kind)
    if book is None:
        return "", []
    steps = book["steps"]
    plan = []
    for i, s in enumerate(steps, 1):
        args = {k: v.format(**h.params) if isinstance(v, str) else v for k, v in s["args"].items()}
        why = f"Runbook '{book['title']}' {i}/{len(steps)}: " + s["why"].format(**h.params)
        plan.append(Action(why, s["tool"], args))
    return book["title"], plan


class IncidentAgent:
    def __init__(self, llm: LLM, telemetry: FileTelemetry, infra: MockInfra, approver: Approver,
                 runbooks_path: Path, on_event: EventHook | None = None, max_steps: int = 15) -> None:
        self.llm, self.telemetry, self.infra, self.approver = llm, telemetry, infra, approver
        self.runbooks = json.loads(Path(runbooks_path).read_text(encoding="utf-8"))
        self.emit = on_event or (lambda kind, data: None)
        self.max_steps = max_steps

    def run(self, alert: Alert) -> tuple[AgentState, SimClock]:
        state = AgentState(alert)
        clock = SimClock(alert.fired_at)
        clock.advance(3)  # the page reaches the agent a few minutes after the alert fires
        registry = build_toolbox(self.telemetry, self.infra, state, self.approver, clock)
        for step in range(1, self.max_steps + 1):
            action = self.llm.next_action(state, registry.catalog())
            self.emit("think", {"step": step, "ts": clock.now(), "thought": action.thought})
            if action.tool == "finish":
                state.status = action.args.get("status", "done")
                self.emit("finish", {"status": state.status})
                return state, clock
            if state.plan and state.plan[0].tool == action.tool:
                state.plan.pop(0)
            tool = registry.tools.get(action.tool)
            self.emit("act", {"tool": action.tool, "args": action.args,
                              "risk": tool.risk.value if tool else "?", "approval": bool(tool and tool.mutating)})
            record, result = registry.execute(action)
            state.records.append(record)
            self.emit("observe", {"record": record})
            if result is not None:
                self._absorb(state, record, result)
        state.status = "step_limit"
        return state, clock

    def _absorb(self, state: AgentState, record: ActionRecord, result: ToolResult) -> None:
        """Copy tool output into the state the LLM will read next turn."""
        tool = record.tool
        if tool == "detect_anomalies":
            state.anomalies = result.data
        elif tool == "search_logs":
            state.signatures = result.data
        elif tool == "list_deploys":
            state.deploys = result.data
        elif tool == "rank_hypotheses":
            state.hypotheses = result.data
            if state.top_hypothesis:
                state.runbook_title, state.plan = load_runbook(self.runbooks, state.top_hypothesis)
                self.emit("plan", {"title": state.runbook_title, "steps": [a.tool for a in state.plan]})
        elif tool == "verify_recovery":
            state.verified = result.data["healthy"]
        elif tool == "page_oncall":
            state.paged = True
