"""Models return text *and* token usage, because usage is what a trace turns into cost."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from .config import load_settings
from .spans import Clock, SimClock

Message = dict[str, str]
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message]) -> Completion: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockLLM:
    """Scripted research assistant. Simulates latency (on the clock) and token usage."""

    name = "mock-llm"

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SimClock()
        self.calls = 0

    def complete(self, system: str, messages: list[Message]) -> Completion:
        self.calls += 1
        question = messages[0]["content"].lower()
        results = [m["content"] for m in messages[1:] if m["role"] == "user"]
        text = self._decide(question, results)
        prompt_tokens = estimate_tokens(system + "".join(m["content"] for m in messages))
        out_tokens = estimate_tokens(text)
        self.clock.sleep(250 + 9 * out_tokens)  # time-to-first-token + generation
        return Completion(text, prompt_tokens, out_tokens)

    @staticmethod
    def _decide(question: str, results: list[str]) -> str:
        done = " ".join(results)
        if "weather" in question and "weather:" not in done:
            city = re.search(r"weather in (\w+)", question)
            return json.dumps({"tool": "weather", "args": {"city": city.group(1) if city else "London"}})
        bill = re.search(r"(\d+(?:\.\d+)?)% tip on a (\d+(?:\.\d+)?)", question)
        if bill and "calculator:" not in done:
            return json.dumps({"tool": "calculator", "args": {"expression": f"{bill.group(2)} * {bill.group(1)} / 100"}})
        if "news" in question and "search:" not in done:
            topic = question.split("about", 1)[-1].strip(" ?.")
            return json.dumps({"tool": "search", "args": {"query": topic}})
        facts = "; ".join(r.split(":", 1)[1].strip() for r in results if ":" in r)
        return json.dumps({"answer": f"Here is what I found: {facts}."})


class AnthropicLLM:
    """Claude via the official `anthropic` SDK (pip install anthropic)."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.name = model or load_settings().llm_model or "claude-opus-5-5"

    def complete(self, system: str, messages: list[Message]) -> Completion:
        kwargs: dict[str, Any] = {"model": self.name, "max_tokens": 16000, "system": system, "messages": messages}
        if self.name in FALLBACK_MODELS:
            response = self.client.beta.messages.create(
                **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        else:
            response = self.client.messages.create(**kwargs)
        text = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "refusal":
            text = json.dumps({"answer": "[the model declined this request]"})
        return Completion(text, response.usage.input_tokens, response.usage.output_tokens)


class OpenAILLM:
    """OpenAI chat completions via the official `openai` SDK (pip install openai)."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self.client = OpenAI()
        self.name = model or load_settings().llm_model or "gpt-4o-mini"

    def complete(self, system: str, messages: list[Message]) -> Completion:
        response = self.client.chat.completions.create(
            model=self.name, messages=[{"role": "system", "content": system}, *messages]
        )
        usage = response.usage
        return Completion(response.choices[0].message.content or "",
                          usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0)


def llm_from_env(default: LLM) -> LLM:
    provider = load_settings().llm_provider
    if provider == "mock":
        return default
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai")
