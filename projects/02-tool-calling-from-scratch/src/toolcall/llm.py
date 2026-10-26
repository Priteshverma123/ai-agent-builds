"""Model backends that speak 'tool calling'.

Our conversation uses one provider-neutral message format:

    {"role": "user",      "content": "What's the weather in Paris?"}
    {"role": "assistant", "content": "", "tool_calls": [ToolCall, ...], "raw": <provider blocks>}
    {"role": "tool",      "results": [ToolResult, ...]}

Each backend translates that format to its own API and back. MockLLM (the default) needs no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import DEFAULT_MODELS, Settings
from .tools import ToolCall, ToolResult

Message = dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # the provider's own assistant content, resent unchanged on the next call


class LLM(Protocol):
    def chat(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse: ...


# --- The offline mock ------------------------------------------------------------

_CITIES = re.compile(r"\b(?:in|and)\s+([A-Z][a-zA-Z]+)")
_MONEY = re.compile(r"([\d.,]+)\s*([A-Z]{3})\s+(?:to|in|into)\s+([A-Z]{3})")
_MATH = re.compile(r"(?:what is|what's|calculate)\s+([\d\s+\-*/().%]+\d\)?)", re.IGNORECASE)


class MockLLM:
    """A rule-based stand-in that behaves like a tool-calling model.

    Turn 1: read the question and decide which tools to call (only tools it was offered).
    Turn 2: read the tool results and write the final answer.
    """

    def chat(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        last = messages[-1]
        if last["role"] == "tool":
            return LLMResponse(" ".join(self._describe(r) for r in last["results"]))
        offered = {t["name"] for t in tools}
        calls = [c for c in self._plan(last["content"]) if c.name in offered]
        if calls:
            return LLMResponse("", calls)
        return LLMResponse("I can check the weather, convert currencies and do exact math. Ask me one of those!")

    @staticmethod
    def _plan(question: str) -> list[ToolCall]:
        calls: list[tuple[str, dict[str, Any]]] = []
        if "weather" in question.lower():
            calls += [("get_weather", {"city": city}) for city in _CITIES.findall(question)]
        if match := _MONEY.search(question):
            amount = float(match.group(1).replace(",", ""))
            calls.append(("convert_currency", {"amount": amount, "from_currency": match.group(2), "to_currency": match.group(3)}))
        if match := _MATH.search(question):
            calls.append(("calculate", {"expression": match.group(1).strip()}))
        return [ToolCall(f"call_{i}", name, args) for i, (name, args) in enumerate(calls, start=1)]

    @staticmethod
    def _describe(result: ToolResult) -> str:
        data = json.loads(result.content)
        if not result.ok:
            return f"Sorry, {result.name} failed ({data['error']})."
        if result.name == "get_weather":
            return f"{data['city']}: {data['temp_c']} C and {data['conditions']}."
        if result.name == "convert_currency":
            return f"{data['amount']:,.2f} {data['from']} = {data['result']:,.2f} {data['to']} (rate {data['rate']})."
        return f"{data['expression']} = {data['result']}."


# --- Real providers (optional) ---------------------------------------------------


class AnthropicLLM:
    """Claude via the official SDK: `pip install anthropic`, set ANTHROPIC_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODELS["anthropic"]

    def chat(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            tools=[{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools],
            messages=[self._convert(m) for m in messages],
            betas=["server-side-fallback-2026-07-01"],  # retry on a fallback model if a classifier declines
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            return LLMResponse("[the model declined to answer]")
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        return LLMResponse(text, calls, raw=response.content)

    @staticmethod
    def _convert(m: Message) -> dict[str, Any]:
        if m["role"] == "user":
            return {"role": "user", "content": m["content"]}
        if m["role"] == "assistant":  # resend Claude's own blocks (incl. thinking) untouched
            return {"role": "assistant", "content": m["raw"]}
        return {  # all results of one round go back in ONE user message
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": not r.ok}
                for r in m["results"]
            ],
        }


class OpenAILLM:
    """OpenAI via the official SDK: `pip install openai`, set OPENAI_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import openai

        self.client = openai.OpenAI()
        self.model = model or DEFAULT_MODELS["openai"]

    def chat(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            converted.extend(self._convert(m))
        response = self.client.chat.completions.create(
            model=self.model,
            messages=converted,
            tools=[{"type": "function", "function": t} for t in tools],
        )
        message = response.choices[0].message
        calls = [self._parse_call(tc) for tc in message.tool_calls or []]
        return LLMResponse(message.content or "", calls)

    @staticmethod
    def _parse_call(tc: Any) -> ToolCall:
        try:
            arguments = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            arguments = {}  # the registry will report the missing arguments back to the model
        return ToolCall(tc.id, tc.function.name, arguments)

    @staticmethod
    def _convert(m: Message) -> list[dict[str, Any]]:
        if m["role"] == "user":
            return [{"role": "user", "content": m["content"]}]
        if m["role"] == "assistant":
            calls = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in m["tool_calls"]
            ]
            return [{"role": "assistant", "content": m["content"] or None, **({"tool_calls": calls} if calls else {})}]
        return [{"role": "tool", "tool_call_id": r.call_id, "content": r.content} for r in m["results"]]


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a backend from settings (env LLM_PROVIDER: mock | anthropic | openai). Default: mock."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.model_for("anthropic"))
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.model_for("openai"))
    return MockLLM()
