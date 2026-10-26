"""The tool-calling loop: ask -> (model asks for tools -> we run them -> feed results back)* -> answer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import LLM, Message
from .tools import ToolRegistry

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the provided tools for weather, currency and arithmetic "
    "instead of guessing. If a tool returns an error, explain it briefly to the user."
)

# on_event(kind, payload) lets the CLI draw a trace without the loop knowing about printing.
EventHandler = Callable[[str, Any], None]


@dataclass
class Run:
    answer: str
    rounds: int
    messages: list[Message] = field(default_factory=list)


def run(
    question: str,
    llm: LLM,
    registry: ToolRegistry,
    max_rounds: int = 5,
    on_event: EventHandler | None = None,
) -> Run:
    emit = on_event or (lambda kind, payload: None)
    messages: list[Message] = [{"role": "user", "content": question}]

    for round_number in range(1, max_rounds + 1):
        response = llm.chat(SYSTEM_PROMPT, messages, registry.schemas())
        messages.append(
            {"role": "assistant", "content": response.text, "tool_calls": response.tool_calls, "raw": response.raw}
        )
        if not response.tool_calls:  # no tools requested: this is the final answer
            emit("answer", response.text)
            return Run(response.text, round_number, messages)

        emit("text", response.text)  # models often say what they're about to do
        results = []
        for call in response.tool_calls:
            emit("call", call)
            result = registry.call(call)
            emit("result", result)
            results.append(result)
        messages.append({"role": "tool", "results": results})

    emit("answer", "[stopped: too many tool rounds]")
    return Run("[stopped: too many tool rounds]", max_rounds, messages)
