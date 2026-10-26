"""LLM backends. MockLLM is the default, so everything runs offline with no API key.

Every backend has the same one-method interface:

    complete(system: str, messages: list[{"role", "content"}]) -> str
"""

from __future__ import annotations

import re
from typing import Protocol

from .config import DEFAULT_MODELS, Settings

ChatMessage = dict[str, str]


class LLM(Protocol):
    def complete(self, system: str, messages: list[ChatMessage]) -> str: ...


# --- The offline mock ------------------------------------------------------------

_NAME = re.compile(r"\bmy name is (\w+)", re.IGNORECASE)
_CITY = re.compile(r"\bi live in ([A-Z][\w ]*?)[.!]?$", re.IGNORECASE)
_LIKE = re.compile(r"\bi (?:like|love) (.+?)[.!]?$", re.IGNORECASE)


class MockLLM:
    """A rule-based stand-in for a real model.

    Like a real model, it has no memory of its own: it can only "remember" facts
    that appear in the messages it is sent. That makes the context window visible.
    """

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        user_lines = [m["content"] for m in messages if m["role"] == "user"]
        latest = user_lines[-1]
        facts = self._facts(user_lines[:-1])
        q = latest.lower()

        if match := _NAME.search(latest):
            return f"Nice to meet you, {match.group(1)}! I'll remember that while it's in my window."
        if match := _CITY.search(latest):
            return f"{match.group(1)} -- lovely. Noted."
        if match := _LIKE.search(latest):
            return f"Good taste. I'll remember you like {match.group(1)}."
        if "my name" in q:
            return self._recall(facts, "name", "Your name is {}.")
        if "where do i live" in q:
            return self._recall(facts, "city", "You live in {}.")
        if "what do i like" in q:
            return self._recall(facts, "like", "You like {}.")
        if "fact" in q:
            return (
                "Octopuses have three hearts, blue blood and neurons in every arm, "
                "so each arm can taste and react on its own."
            )
        return f"I can see {len(messages)} message(s) in my window. Ask me what I remember!"

    @staticmethod
    def _facts(user_lines: list[str]) -> dict[str, str]:
        facts: dict[str, str] = {}
        for line in user_lines:
            for key, pattern in (("name", _NAME), ("city", _CITY), ("like", _LIKE)):
                if match := pattern.search(line):
                    facts[key] = match.group(1)
        return facts

    @staticmethod
    def _recall(facts: dict[str, str], key: str, template: str) -> str:
        if key in facts:
            return template.format(facts[key])
        return "I don't know. If you told me, it has scrolled out of my context window."


# --- Real providers (optional) ---------------------------------------------------


class AnthropicLLM:
    """Claude via the official SDK: `pip install anthropic`, set ANTHROPIC_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # imported lazily: the offline path needs no SDK

        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODELS["anthropic"]

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=messages,
            # If a safety classifier declines, retry on a fallback model server-side.
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            return "[the model declined to answer]"
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAILLM:
    """OpenAI via the official SDK: `pip install openai`, set OPENAI_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import openai

        self.client = openai.OpenAI()
        self.model = model or DEFAULT_MODELS["openai"]

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a backend from settings (env LLM_PROVIDER: mock | anthropic | openai). Default: mock."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.model_for("anthropic"))
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.model_for("openai"))
    return MockLLM()
