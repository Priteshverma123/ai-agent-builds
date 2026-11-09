"""LLM adapters: one tiny interface, a deterministic offline model that counts its calls, a real provider.

Counting calls matters here: the tests prove that a resumed run does **not** ask the model again
for steps it already finished. LLM output is non-deterministic and costs money, so a durable
workflow journals it like any other side effect.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import Settings

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class ProviderLLM:
    """A real model behind the same interface. SDKs are imported lazily so they stay optional."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {provider!r}")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.name = f"{provider}:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        if self.provider == "anthropic":
            import anthropic  # pip install anthropic

            response = anthropic.Anthropic().messages.create(
                model=self.model, max_tokens=16000, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in response.content if block.type == "text")
        from openai import OpenAI  # pip install openai

        response = OpenAI().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


def llm_from_env(default: LLM, settings: Settings | None = None) -> LLM:
    """Return a real provider if ``LLM_PROVIDER`` asks for one, otherwise the offline default."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "mock":
        return default
    return ProviderLLM(settings.llm_provider, settings.llm_model)


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:80]!r}")
    return json.loads(match.group(0))


class MockLLM:
    """Summarises tickets and drafts an email deterministically, and counts how often it's asked."""

    name = "mock-llm"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        if prompt.startswith("TASK: summarize"):
            tickets = json.loads(prompt.split("TICKETS:", 1)[1])
            open_ = [t for t in tickets if t["status"] == "open"]
            summary = (f"{len(tickets)} tickets this week: {len(tickets) - len(open_)} resolved, {len(open_)} open"
                       + (f" (top priority: {open_[0]['title']})" if open_ else "") + ".")
            return json.dumps({"summary": summary, "needs_attention": bool(open_)})
        summary = prompt.split("SUMMARY:", 1)[1].strip()
        return json.dumps({"subject": "Your weekly support digest",
                           "body": f"Hi team,\n\n{summary}\n\nWe're on it and will update you by Friday.\n\n- Support"})
