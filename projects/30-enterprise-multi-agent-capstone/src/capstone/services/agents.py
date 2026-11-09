"""Specialist agents (recap of 11 and 19). Each one has a single job and a minimal tool allow-list."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from capstone.adapters.llm import LLM
from capstone.adapters.mcp import ScopedTools
from capstone.domain.models import Blackboard, Chunk, Hit, Step
from capstone.services import guardrails
from capstone.services.tracing import Trace


@dataclass
class AgentContext:
    """Everything a specialist may touch during one step. Tools go through tracing and the allow-list."""

    board: Blackboard
    llm: LLM
    trace: Trace
    tools: ScopedTools
    notes: list[str] = field(default_factory=list)

    def tool(self, name: str, **arguments: Any) -> Any:
        with self.trace.span(name, "tool", args=_short(arguments)) as span:
            result = self.tools.call(name, **arguments)
            self.board.tools_used.append(name)
            span.set(result=_short(result))
            return result


def _short(value: Any, limit: int = 60) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


class Specialist(Protocol):
    name: str
    description: str
    allowed_tools: frozenset[str]

    def run(self, step: Step, ctx: AgentContext) -> None: ...


class ResearchAgent:
    name, description = "research", "Finds and cites handbook passages"
    allowed_tools = frozenset({"search_docs"})

    def run(self, step: Step, ctx: AgentContext) -> None:
        for row in ctx.tool("search_docs", query=ctx.board.question, k=3):
            hit = Hit(Chunk(row["id"], row["source"], row["section"], row["text"]), row["score"])
            verdict = guardrails.check_tool_output(row["text"])
            if verdict.allowed:
                ctx.board.findings.append(hit)
                continue
            ctx.board.quarantined.append(hit)
            ctx.notes.extend(f"{r} in {row['id']}" for r in verdict.reasons)
            with ctx.trace.span("tool-output", "guard", chunk=row["id"]) as s:
                s.status = "quarantined"


class AnalystAgent:
    name, description = "analyst", "Does arithmetic on cited numbers with the calculator tool"
    allowed_tools = frozenset({"calculate"})

    def run(self, step: Step, ctx: AgentContext) -> None:
        expression = ctx.llm.calculation_for(ctx.board.question, ctx.board)
        if expression is None:
            ctx.notes.append("analyst: no rate and quantity found to calculate")
            return
        ctx.board.calculation = ctx.tool("calculate", expression=expression)


class OpsAgent:
    name, description = "ops", "Opens Ops tickets (the only agent allowed to change anything)"
    allowed_tools = frozenset({"create_ticket"})

    def run(self, step: Step, ctx: AgentContext) -> None:
        fields = ctx.llm.ticket_for(ctx.board.question)
        ctx.board.ticket = ctx.tool("create_ticket", title=fields["title"], priority=fields["priority"])


class WriterAgent:
    name, description = "writer", "Writes the final answer with [n] citations; has no tools"
    allowed_tools: frozenset[str] = frozenset()

    def run(self, step: Step, ctx: AgentContext) -> None:
        with ctx.trace.span("write_answer", "llm", findings=len(ctx.board.findings)):
            ctx.board.draft = ctx.llm.write_answer(ctx.board.question, ctx.board)


def default_specialists() -> dict[str, Specialist]:
    return {a.name: a for a in (ResearchAgent(), AnalystAgent(), OpsAgent(), WriterAgent())}
