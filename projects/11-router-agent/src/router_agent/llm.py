"""LLM clients. ``MockRouterLLM`` is deterministic and used by default and in tests.

The mock is a tiny *few-shot nearest-neighbour classifier*: it reads the labelled
examples from the prompt (exactly what a real model would see), compares the message
to each one with bag-of-words cosine similarity, and turns the gap between the best
and second-best intent into a confidence. Close scores mean low confidence.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Protocol

from .config import Settings

STOPWORDS = frozenset("a an and are be can do for how i in is it me my of on the to we what with you your".split())
SYNONYMS = {"sign": "login", "log": "login", "card": "payment", "bill": "charged", "cost": "price",
            "much": "price", "discounts": "discount", "seats": "team", "people": "team", "teams": "team",
            "file": "export", "data": "export", "csv": "export", "crashing": "crash", "crashes": "crash"}


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text`` (real models sometimes add prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:80]!r}")
    return json.loads(match.group(0))


def bag(text: str) -> Counter:
    words = re.findall(r"[a-z]+", text.lower())
    return Counter(SYNONYMS.get(w, w) for w in words if w not in STOPWORDS)


def cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[k] * b[k] for k in a)
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


class MockRouterLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        if "TASK: CLASSIFY" not in system:
            raise ValueError("MockRouterLLM only knows TASK: CLASSIFY")
        message = bag(prompt.rsplit("Message:", 1)[1])
        best: dict[str, tuple[float, str]] = {}
        for intent, example in re.findall(r"^\s*example \((\w+)\): (.+)$", prompt, re.MULTILINE):
            score = cosine(message, bag(example))
            if score > best.get(intent, (-1.0, ""))[0]:
                best[intent] = (score, example)
        ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)
        (top, (top_score, example)), (_, (second_score, _)) = ranked[0], ranked[1]
        if top_score < 0.15:
            return json.dumps({"intent": "fallback", "confidence": 0.9, "reason": "no example is similar"})
        # Confidence grows with the absolute match AND with the margin over the runner-up.
        confidence = min(0.99, 0.5 * top_score + 0.5 * (top_score - second_score) / top_score + 0.2)
        return json.dumps({"intent": top, "confidence": round(confidence, 2),
                           "reason": f'closest example: "{example}"'})


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or "claude-opus-5-5"
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
        self.model = model or "gpt-4.1-mini"
        self.name = f"openai:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from ``settings.llm_provider`` (env ``LLM_PROVIDER``, default: mock)."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockRouterLLM()
