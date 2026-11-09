"""The orchestrator: guard -> plan -> delegate -> guard -> answer, all inside one trace (recap of 10, 19)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from capstone.adapters.llm import LLM
from capstone.adapters.mcp import McpClient, ScopedTools, ToolError
from capstone.domain.models import AskResponse, Blackboard, CitationOut
from capstone.services import guardrails
from capstone.services.agents import AgentContext, Specialist
from capstone.services.tracing import Trace, TraceStore

REFUSAL = "I can't help with that request. It looks like an attempt to override my instructions."


@dataclass
class Orchestrator:
    llm: LLM
    client: McpClient
    specialists: dict[str, Specialist]
    traces: TraceStore
    max_steps: int = 6

    def ask(self, question: str) -> tuple[AskResponse, Trace]:
        trace = self.traces.new()
        try:
            with trace.span("ask", "request"):
                response = self._ask(question, trace)
        finally:
            self.traces.save(trace)
        return response, trace

    def _ask(self, question: str, trace: Trace) -> AskResponse:
        notes: list[str] = []
        with trace.span("input", "guard") as s:
            verdict = guardrails.check_input(question)
            notes += verdict.reasons
            s.set(allowed=verdict.allowed)
            if not verdict.allowed:
                s.status = "blocked"
                return AskResponse(answer=REFUSAL, blocked=True, citations=[], plan=[], tools_used=[],
                                   guardrail_notes=notes, trace_id=trace.id)
        board = Blackboard(question=verdict.text)

        with trace.span("plan", "plan") as s:
            plan = self.llm.plan(board.question, {n: a.description for n, a in self.specialists.items()})
            s.set(steps=" > ".join(st.agent for st in plan.steps))

        for step in plan.steps[: self.max_steps]:
            agent = self.specialists[step.agent]
            ctx = AgentContext(board, self.llm, trace,
                               ScopedTools(self.client, set(agent.allowed_tools)), notes)
            with trace.span(step.agent, "agent", tools=",".join(sorted(agent.allowed_tools)) or "-") as s:
                try:
                    agent.run(step, ctx)
                except (PermissionError, ToolError) as exc:
                    s.status = "failed"
                    notes.append(f"{step.agent}: {exc}")

        with trace.span("output", "guard") as s:
            out = guardrails.check_output(board.draft, needs_citation=bool(board.findings))
            notes += out.reasons
            s.set(notes=len(out.reasons))

        cited = {int(n) for n in re.findall(r"\[(\d+)\]", out.text)}
        return AskResponse(
            answer=out.text, blocked=False,
            citations=[CitationOut(n=c.n, source=c.source, section=c.section)
                       for c in board.citations() if c.n in cited],
            plan=[st.agent for st in plan.steps], tools_used=board.tools_used,
            guardrail_notes=notes, trace_id=trace.id)
