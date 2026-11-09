"""LLM clients with native tool calling. ``MockLLM`` is deterministic and used by default and in tests.

All clients share one small interface:
    start(system, task, tools)        begin a conversation
    next_turn(results) -> Turn        send the latest tool results, get the model's next move
A ``Turn`` either asks for tool calls or gives the final answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    text: str
    is_error: bool


@dataclass
class Turn:
    thought: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    answer: str | None = None


class LLM(Protocol):
    name: str

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None: ...

    def next_turn(self, results: list[ToolResult]) -> Turn: ...


class MockLLM:
    """A rule-based "model". Like a real one, it only knows the tools it was *given* at runtime.

    It finds tools by suffix (``*__calculate``), so it works whatever the server is called,
    and it reads tool errors and retries, the way a real model self-corrects.
    """

    name = "mock"

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        self.task = task
        self.tools = [t["name"] for t in tools]
        self.resources = re.findall(r"^- (\S+://\S+): (.+)$", system, re.MULTILINE)
        self.history: list[ToolResult] = []
        self._calls = 0

    def _tool(self, suffix: str) -> str | None:
        return next((t for t in self.tools if t == suffix or t.endswith("__" + suffix)), None)

    def _call(self, thought: str, name: str, arguments: dict[str, Any]) -> Turn:
        self._calls += 1
        return Turn(thought=thought, tool_calls=[ToolCall(f"call_{self._calls}", name, arguments)])

    def next_turn(self, results: list[ToolResult]) -> Turn:
        self.history += results
        task = self.task.lower()
        if not self.history:
            return self._first_move(task)
        last = self.history[-1]
        if last.is_error:
            return self._recover(last)
        if last.name == "read_resource" and "hours" in task and (days := re.search(r"(\d+) days", last.text)):
            calc = self._tool("calculate")
            if calc:
                return self._call(f"The handbook says {days.group(0)}. Convert to hours.", calc,
                                  {"expression": f"{days.group(1)} * 24"})
        return Turn(thought="I have what I need.", answer=self._answer(last))

    def _first_move(self, task: str) -> Turn:
        if any(w in task for w in ("handbook", "policy", "policies")) and self._tool("read_resource"):
            uri = next((u for u, d in self.resources if "handbook" in (u + d).lower()), None)
            if uri:
                return self._call(f"This is a policy question; read {uri} first.", "read_resource", {"uri": uri})
        percent = re.search(r"(\d+(?:\.\d+)?)% of ([\d,.]+)", task)
        math = re.search(r"\d[\d.,\s]*[-+*/][\d.,\s()+\-*/]*\d", task)
        if (percent or math) and (calc := self._tool("calculate")):
            expression = percent.group(0) if percent else math.group(0).strip()
            return self._call("Arithmetic: use the calculator instead of guessing.", calc, {"expression": expression})
        if "remember" in task and (add := self._tool("add_note")):
            body = re.split(r"remember (?:that )?", self.task, flags=re.IGNORECASE)[-1].strip(" .")
            tags = re.findall(r"#(\w+)", body)
            body = re.sub(r"\s*#\w+", "", body)
            return self._call("The user wants this saved.", add, {"title": body[:40], "body": body, "tags": tags})
        if re.search(r"\b(find|search|look up)\b", task) and (search := self._tool("search_notes")):
            query = re.sub(r".*\b(?:find|search|look up)\b|\b(my|notes?|about|for|the)\b|[?.]", " ", task)
            return self._call("Search the notebook.", search, {"query": " ".join(query.split())})
        return Turn(thought="None of my tools fit.", answer="I don't have a tool that can help with that.")

    def _recover(self, last: ToolResult) -> Turn:
        attempts = sum(1 for r in self.history if r.is_error)
        percent = re.search(r"(\d+(?:\.\d+)?)% of ([\d,.]+)", self.task)
        if attempts == 1 and last.name.endswith("calculate") and percent:
            fixed = f"{percent.group(2).replace(',', '')} * {percent.group(1)} / 100"
            return self._call(f"The tool rejected '% of'. Rewrite it as plain arithmetic: {fixed}.",
                              last.name, {"expression": fixed})
        return Turn(thought="The tool keeps failing.", answer=f"Sorry, I could not do that: {last.text}")

    def _answer(self, last: ToolResult) -> str:
        if last.name.endswith("calculate"):
            value = json.loads(last.text)["result"]
            value = int(value) if float(value).is_integer() else value
            days = re.search(r"(\d+) days", self.history[0].text)
            if self.history[0].name == "read_resource" and days:
                return f"The handbook gives a {days.group(1)}-day refund window, which is {value} hours."
            return f"The answer is {value}."
        if last.name.endswith("add_note"):
            note = json.loads(last.text)
            return f"Saved as note #{note['id']} with tags {note['tags']}."
        if last.name.endswith("search_notes"):
            found = json.loads(last.text)
            titles = "; ".join(f"#{n['id']} {n['title']}" for n in found["notes"])
            return f"I found {found['count']} note(s): {titles}." if found["count"] else "No matching notes."
        sentence = next((s for s in re.split(r"(?<=\.)\s+", last.text) if "refund" in s.lower()), last.text[:200])
        return f"The handbook says: {sentence.strip()}"


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or "claude-opus-5-5"
        self.name = f"anthropic:{self.model}"

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        self.system = system
        self.tools = tools  # already {name, description, input_schema}: the Anthropic shape
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    def next_turn(self, results: list[ToolResult]) -> Turn:
        if results:  # all results of one turn go back together, in a single user message
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.text, "is_error": r.is_error}
                for r in results]})
        response = self.client.messages.create(
            model=self.model, max_tokens=16000, system=self.system, tools=self.tools, messages=self.messages)
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        self.messages.append({"role": "assistant", "content": response.content})  # keep every block
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
        return Turn(thought=text, tool_calls=calls) if calls else Turn(answer=text)


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        import openai  # optional dependency: pip install openai

        self.client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.model = model or "gpt-4.1-mini"
        self.name = f"openai:{self.model}"

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in tools]
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": task}]

    def next_turn(self, results: list[ToolResult]) -> Turn:
        self.messages += [{"role": "tool", "tool_call_id": r.call_id, "content": r.text} for r in results]
        message = self.client.chat.completions.create(
            model=self.model, messages=self.messages, tools=self.tools).choices[0].message
        self.messages.append(message.model_dump(exclude_none=True))
        calls = [ToolCall(c.id, c.function.name, json.loads(c.function.arguments or "{}"))
                 for c in message.tool_calls or []]
        return Turn(thought=message.content or "", tool_calls=calls) if calls else Turn(answer=message.content or "")


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from ``settings.llm_provider`` (env ``LLM_PROVIDER``, default: mock)."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockLLM()
