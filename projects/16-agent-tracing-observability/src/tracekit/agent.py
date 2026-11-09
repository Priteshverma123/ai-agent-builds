"""A small tool-using agent. Notice there is almost no tracing code in here: the seams do it."""

from __future__ import annotations

import json

from .instrument import TracedLLM, TracedTools
from .spans import Tracer

SYSTEM_PROMPT = """You are a research assistant with tools: weather(city), calculator(expression), search(query).
Reply with ONE JSON object: {"tool": "<name>", "args": {...}} or {"answer": "<text>"}."""


class Agent:
    def __init__(self, llm: TracedLLM, tools: TracedTools, tracer: Tracer,
                 max_steps: int = 6, retries: int = 1) -> None:
        self.llm, self.tools, self.tracer = llm, tools, tracer
        self.max_steps, self.retries = max_steps, retries

    def run(self, question: str) -> str:
        with self.tracer.span("agent.run", kind="agent", question=question) as root:
            messages = [{"role": "user", "content": question}]
            for step in range(1, self.max_steps + 1):
                with self.tracer.span(f"step {step}", kind="step"):
                    reply = _parse(self.llm.complete(SYSTEM_PROMPT, messages).text)
                    messages.append({"role": "assistant", "content": json.dumps(reply)})
                    if "answer" in reply:
                        root.set("answer", reply["answer"])
                        root.set("steps", step)
                        return str(reply["answer"])
                    observation = self._call_with_retry(str(reply.get("tool")), dict(reply.get("args") or {}))
                    messages.append({"role": "user", "content": observation})
            root.status = "error"
            root.set("error", "step limit reached")
            return "Stopped: step limit reached."

    def _call_with_retry(self, tool: str, args: dict) -> str:
        for attempt in range(1, self.retries + 2):
            try:
                return self.tools.call(tool, args)
            except Exception as exc:  # the tool span already recorded the error
                if attempt > self.retries:
                    return f"error: {tool} failed: {exc}"
                self.tracer.event("retry", tool=tool, attempt=attempt + 1, reason=type(exc).__name__)
        return f"error: {tool} failed"


def _parse(text: str) -> dict:
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return data if isinstance(data, dict) else {"answer": text}
    except ValueError:
        return {"answer": text}
