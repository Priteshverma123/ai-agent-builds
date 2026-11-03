"""LLM clients. ``MockMemoryLLM`` is deterministic and used by default and in tests.

The agent uses the model for three jobs, named by a ``TASK:`` line in the system prompt:
EXTRACT durable facts, SUMMARIZE evicted turns, and RESPOND to the user. The mock only
sees what is in the prompt, exactly like a real model, so if recall fails, it fails too.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import Settings


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text`` (real models sometimes add prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:80]!r}")
    return json.loads(match.group(0))


# (pattern, kind, slot template, importance, text template) for the mock extractor
FACT_RULES = [
    (r"my name is (\w+)", "profile", "name", 0.9, "User's name is {0}"),
    (r"i (?:live in|moved to) (\w+)", "profile", "city", 0.7, "User lives in {0}"),
    (r"i'?m (vegetarian|vegan)", "preference", "diet", 0.8, "User is {0}"),
    (r"allergic to (\w+)", "preference", "allergy:{0}", 1.0, "User is allergic to {0}"),
    (r"training for (a [\w -]+?(?: in \w+)?)[.!]", "goal", "training", 0.7, "User is training for {0}"),
    (r"remember that (.+?)[.!]?$", "note", None, 0.6, "{0}"),
]


class MockMemoryLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        for task, handler in (("EXTRACT", self._extract), ("SUMMARIZE", self._summarize), ("RESPOND", self._respond)):
            if f"TASK: {task}" in system:
                return handler(prompt)
        raise ValueError("MockMemoryLLM got a system prompt without a known TASK")

    def _extract(self, prompt: str) -> str:
        message = prompt.split("Message:", 1)[1].strip()
        facts = []
        for pattern, kind, slot, importance, template in FACT_RULES:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                value = match.group(1)
                facts.append({"text": template.format(value), "kind": kind, "importance": importance,
                              "slot": slot.format(value).lower() if slot else None})
        return json.dumps({"facts": facts})

    def _summarize(self, prompt: str) -> str:
        current = re.search(r"Current summary: (.*)", prompt).group(1).strip()
        said = [line[6:].split(".")[0].strip() for line in prompt.splitlines() if line.startswith("user: ")]
        new = "; ".join(f'user: "{" ".join(s.split()[:6])}..."' for s in said)
        parts = [p for p in (current if current != "(none)" else "", new) if p]
        return "; ".join(parts)

    def _respond(self, prompt: str) -> str:
        memories = re.findall(r"^- \(\w+\) (.+)$", prompt, re.MULTILINE)
        message = prompt.rsplit("User message:", 1)[1].strip().lower()
        known = " | ".join(memories)
        name = re.search(r"User's name is (\w+)", known)
        greeting = f"{name.group(1)}, " if name else ""

        if "where do i live" in message:
            city = re.search(r"User lives in (\w+)", known)
            return f"You live in {city.group(1)}." if city else "I don't know where you live yet."
        if any(w in message for w in ("eat", "dinner", "lunch", "meal", "cook")):
            return self._suggest_food(known, greeting)
        if "Facts I already knew:" in prompt:
            return f"I know, {greeting}that's already in my memory." if greeting else "I know, that's already in my memory."
        if "New facts I just stored:" in prompt:
            return f"Got it, {greeting}I'll remember that." if greeting else "Got it, I'll remember that."
        return "Tell me more!"

    @staticmethod
    def _suggest_food(known: str, greeting: str) -> str:
        diet = re.search(r"User is (vegetarian|vegan)", known)
        allergy = re.search(r"allergic to (\w+)", known)
        training = re.search(r"training for ([\w -]+)", known)
        dish = "a chickpea and spinach curry with rice" if diet else "grilled chicken with rice"
        reasons = [diet.group(1) if diet else None, f"no {allergy.group(1)}" if allergy else None]
        reply = f"{greeting}how about {dish} ({', '.join(r for r in reasons if r) or 'simple and filling'})?"
        if training:
            reply += f" It's carb-rich, good fuel while you're training for {training.group(1).split(' in ')[0]}."
        return reply[0].upper() + reply[1:]


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
    return MockMemoryLLM()
