"""LLM adapters: one tiny interface, a scripted offline debater, an optional real provider."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

from .config import Settings, load_settings

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
    settings = settings or load_settings()
    if settings.use_mock:
        return default
    return ProviderLLM(settings.llm_provider, settings.llm_model)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:80]!r}")
    return json.loads(match.group(0))


def _line(prompt: str, label: str) -> str:
    match = re.search(rf"^{label}:\s*(.+)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


class MockDebateLLM:
    """Replays scripted arguments from ``examples/debates.json``.

    It reads ``AGENT``, ``ROUND`` and ``QUESTION`` from the prompt - the same prompt a real model
    gets - and answers with the scripted JSON. A round with no script repeats the last one, which
    is how a stubborn debater behaves.
    """

    name = "mock-debater"

    def __init__(self, script_path: Path) -> None:
        self.questions = json.loads(Path(script_path).read_text(encoding="utf-8"))["questions"]

    def complete(self, system: str, prompt: str) -> str:
        question, agent, rnd = _line(prompt, "QUESTION"), _line(prompt, "AGENT"), int(_line(prompt, "ROUND"))
        entry = next((q for q in self.questions.values() if q["text"] == question), None)
        if entry is None or agent not in entry["script"]:
            return "I have no strong opinion on this."
        rounds = entry["script"][agent]
        scripted = max(int(r) for r in rounds if int(r) <= rnd)
        return json.dumps(rounds[str(scripted)])
