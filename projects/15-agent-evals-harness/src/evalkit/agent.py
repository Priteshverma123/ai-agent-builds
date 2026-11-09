"""The system under test: a small support agent with one tool. Evals treat it as a black box."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .llm import LLM

ORDERS: dict[str, dict[str, str]] = {
    "1001": {"status": "shipped", "tracking": "TRK-55821"},
    "1002": {"status": "processing"},
}

SYSTEM_PROMPT = """You are the support assistant for shop.example.
Policies: returns within 30 days; shipping is $4.99 plus $1.50 per extra item; support email
support@shop.example; support hours 9am-5pm Mon-Fri. Never create discount codes.
Tool: order_status(order_id) -> JSON record ({} if unknown).
Reply with ONE JSON object: {"tool": "order_status", "args": {"order_id": "..."}} or {"answer": "..."}."""


@dataclass
class AgentOutput:
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    steps: int = 0


class SupportAgent:
    def __init__(self, llm: LLM, max_steps: int = 4) -> None:
        self.llm, self.max_steps = llm, max_steps

    @property
    def name(self) -> str:
        return self.llm.name

    def run(self, question: str) -> AgentOutput:
        messages = [{"role": "user", "content": question}]
        out = AgentOutput(answer="")
        for out.steps in range(1, self.max_steps + 1):
            reply = _parse(self.llm.complete(SYSTEM_PROMPT, messages))
            messages.append({"role": "assistant", "content": json.dumps(reply)})
            if "answer" in reply:
                out.answer = str(reply["answer"])
                return out
            order_id = str(reply.get("args", {}).get("order_id", ""))
            out.tool_calls.append(f"order_status({order_id})")
            messages.append({"role": "user", "content": json.dumps(ORDERS.get(order_id, {}))})
        out.answer = "[no answer: step limit]"
        return out


def _parse(text: str) -> dict:
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    return {"answer": text}
