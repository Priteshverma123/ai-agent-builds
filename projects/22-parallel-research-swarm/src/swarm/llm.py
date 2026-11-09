"""LLM adapters for the two model roles: the **planner** (split the question) and the **extractor**
(pull claims out of one document). Offline mocks by default; a real provider via ``LLM_PROVIDER``."""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import Settings, load_settings
from .corpus import stem, terms

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


_BATTERY_PLAN = {"subquestions": [
    {"id": "cost", "question": "How much does a home battery cost?",
     "keywords": ["cost", "price", "installed", "rebate"]},
    {"id": "lifespan", "question": "How long do home batteries last?",
     "keywords": ["warranty", "last", "cycles", "degrade", "lifespan"]},
    {"id": "safety", "question": "Are home batteries safe?",
     "keywords": ["safety", "fire", "thermal", "runaway"]},
    {"id": "savings", "question": "Do home batteries save money?",
     "keywords": ["save", "saved", "savings", "bill", "payback", "tariff"]},
]}


class MockPlanner:
    """Splits the demo question into four sub-questions; anything else becomes a single slice."""

    name = "mock-planner"

    def complete(self, system: str, prompt: str) -> str:
        question = _line(prompt, "QUESTION")
        if "batter" in question.lower():
            return json.dumps(_BATTERY_PLAN)
        keywords = sorted({t for t in terms(question) if len(t) > 3})[:6] or ["overview"]
        return json.dumps({"subquestions": [{"id": "main", "question": question, "keywords": keywords}]})


class MockExtractor:
    """Quotes every sentence of the document that mentions one of the sub-question's keywords."""

    name = "mock-extractor"

    def complete(self, system: str, prompt: str) -> str:
        keywords = {stem(k.strip().lower()) for k in _line(prompt, "KEYWORDS").split(",")}
        document = prompt.split("DOCUMENT:\n", 1)[1]
        sentences = [s.strip() for s in document.splitlines() if s.strip()]
        return json.dumps({"claims": [s for s in sentences if keywords & set(terms(s))]})
