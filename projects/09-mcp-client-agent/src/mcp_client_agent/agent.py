"""The agent loop: give the model the tools discovered over MCP, run its calls, feed results back."""

from __future__ import annotations

from .hub import MCPHub
from .llm import LLM, ToolResult
from .trace import Trace

SYSTEM_TEMPLATE = """You are a helpful team assistant. Use the tools to get facts; never guess numbers.
Tool names look like <server>__<tool>. If a tool returns an error, read it and try again differently.

Connected MCP servers:
{servers}

Resources you can read with read_resource:
{resources}"""


def build_system_prompt(hub: MCPHub) -> str:
    servers = "\n".join(f"- {c.name}: {c.server_info.get('name', '?')} {c.server_info.get('version', '')}. "
                        f"{c.instructions}" for c in hub.clients.values())
    resources = "\n".join(f"- {r['uri']}: {r.get('description') or r['name']}" for r in hub.resources) or "(none)"
    return SYSTEM_TEMPLATE.format(servers=servers, resources=resources)


class MCPAgent:
    def __init__(self, hub: MCPHub, llm: LLM, max_steps: int = 6, trace: Trace | None = None) -> None:
        self.hub = hub
        self.llm = llm
        self.max_steps = max_steps
        self.trace = trace or Trace(quiet=True)

    def run(self, task: str) -> str:
        self.trace.row("user", task)
        self.llm.start(build_system_prompt(self.hub), task, self.hub.tool_specs())
        results: list[ToolResult] = []
        for step in range(1, self.max_steps + 1):
            turn = self.llm.next_turn(results)
            if turn.thought:
                self.trace.row("think", f"(step {step}) {turn.thought}")
            if not turn.tool_calls:
                answer = turn.answer or ""
                self.trace.row("answer", answer)
                return answer
            results = []
            for call in turn.tool_calls:
                tool = self.hub.tools.get(call.name)
                where = f"{tool.server}: tools/call {tool.name}" if tool else "resources/read"
                self.trace.row("call", f"{call.name}({call.arguments})  -> {where}")
                outcome = self.hub.call(call.name, call.arguments)
                self.trace.row("error" if outcome.is_error else "result", " ".join(outcome.text.split())[:160])
                results.append(ToolResult(call.id, call.name, outcome.text, outcome.is_error))
        answer = f"Stopped after {self.max_steps} steps without a final answer."
        self.trace.row("answer", answer)
        return answer
