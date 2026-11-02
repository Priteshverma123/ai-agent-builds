"""LLM clients. ``MockResearchLLM`` is deterministic and used by default and in tests.

Every client has one method, ``complete(system, prompt) -> str``. The agent tells the
model which job it is doing with a ``TASK:`` line in the system prompt, so the mock can
answer each job with simple, readable rules. Set ``LLM_PROVIDER=anthropic`` or
``LLM_PROVIDER=openai`` to use a real model instead (install that provider's SDK first).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import DEFAULT_MODELS, Settings
from .corpus import split_sentences, tokenize


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text`` (real models sometimes wrap it in prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:80]!r}")
    return json.loads(match.group(0))


def _field(prompt: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.*)$", prompt, re.MULTILINE)
    return match.group(1).strip() if match else ""


class MockResearchLLM:
    """Rule-based stand-in for a model. Good enough to show every step of the agent."""

    name = "mock"
    ASPECTS = ("", "evidence study", "cost drawbacks")  # overview, evidence, trade-offs

    def complete(self, system: str, prompt: str) -> str:
        if "TASK: PLAN" in system:
            return self._plan(prompt)
        if "TASK: EXTRACT" in system:
            return self._extract(prompt)
        if "TASK: WRITE" in system:
            return self._write(prompt)
        raise ValueError("MockResearchLLM got a system prompt without a known TASK")

    def _plan(self, prompt: str) -> str:
        topic = " ".join(tokenize(_field(prompt, "Question")))
        return json.dumps({"queries": [f"{topic} {aspect}".strip() for aspect in self.ASPECTS]})

    def _extract(self, prompt: str) -> str:
        wanted = set(tokenize(_field(prompt, "Question") + " " + _field(prompt, "Focus")))
        source = prompt.split("Source:", 1)[1]

        def score(sentence: str) -> float:
            overlap = len(wanted & set(tokenize(sentence)))
            return overlap + (0.5 if re.search(r"\d", sentence) else 0)  # facts usually have numbers

        ranked = sorted(split_sentences(source), key=score, reverse=True)
        return json.dumps({"claims": [s for s in ranked[:2] if score(s) >= 3]})

    def _write(self, prompt: str) -> str:
        notes = re.findall(r"^\[(\d+)\] \((\w+)\) (.+)$", prompt, re.MULTILINE)
        solid = [f"- {claim} [{sid}]" for sid, kind, claim in notes if kind != "opinion"]
        contested = [f"- {claim} [{sid}] (opinion piece; check against the studies)" for sid, kind, claim in notes if kind == "opinion"]
        sources = len({sid for sid, _, _ in notes})
        lines = ["Key findings", *solid]
        if contested:
            lines += ["", "Contested claims", *contested]
        lines += ["", "Bottom line", f"- {len(solid)} supported findings from {sources} sources; {len(contested)} contested claim(s) flagged."]
        return "\n".join(lines)


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or DEFAULT_MODELS["anthropic"]
        self.name = f"anthropic:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=16000, system=system, messages=[{"role": "user", "content": prompt}]
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        import openai  # optional dependency: pip install openai

        self.client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.model = model or DEFAULT_MODELS["openai"]
        self.name = f"openai:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from settings (env ``LLM_PROVIDER``: mock | anthropic | openai; default mock)."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.model_for("anthropic"))
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.model_for("openai"))
    return MockResearchLLM()
