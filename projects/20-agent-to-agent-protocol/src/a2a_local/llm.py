"""LLM clients for the planner. ``MockLLM`` is deterministic and used by default and in tests.

The planner uses the model for three jobs, named by a ``TASK:`` line in the system prompt:
PLAN (split the request into one sub-task per remote skill, as JSON), FOLLOWUP (answer a
remote agent's question from the user's request) and SUMMARIZE (write the final answer).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import DEFAULT_MODELS, Settings, load_settings

CITY_CURRENCY = {"toronto": "CAD", "vancouver": "CAD", "new york": "USD", "chicago": "USD", "sydney": "AUD",
                 "melbourne": "AUD"}
CURRENCY_WORDS = {"yen": "JPY", "euros": "EUR", "euro": "EUR", "pounds": "GBP", "rupees": "INR"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text`` (real models sometimes add prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:80]!r}")
    return json.loads(match.group(0))


class MockLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        for task, handler in (("PLAN", self._plan), ("FOLLOWUP", self._followup), ("SUMMARIZE", self._summarize)):
            if f"TASK: {task}" in system:
                return handler(prompt)
        raise ValueError("MockLLM got a system prompt without a known TASK")

    @staticmethod
    def _request(prompt: str) -> str:
        return re.search(r"^Request: (.+)$", prompt, re.MULTILINE).group(1)

    def _plan(self, prompt: str) -> str:
        request = self._request(prompt)
        lowered = request.lower()
        skills = re.findall(r"^- (\w+) \| tags: ([\w, ]+)$", prompt, re.MULTILINE)
        subtasks = []
        for skill_id, tags in skills:
            tags = {t.strip() for t in tags.split(",")}
            if {"currency", "money"} & tags and (amount := re.search(r"(\d[\d,]*)\s+(\w+)", request)):
                target = next((code for word, code in CURRENCY_WORDS.items() if word in lowered), "USD")
                subtasks.append({"skill": skill_id, "text": f"Convert {amount.group(1)} {amount.group(2)} to {target}."})
            elif {"weather", "packing"} & tags and ("pack" in lowered or "weather" in lowered):
                city = re.search(r"\bto ([A-Z][a-z]+)", request)
                month = next((m for m in MONTHS if m.lower() in lowered), "")
                if city:
                    subtasks.append({"skill": skill_id, "text": f"What should I pack for {city.group(1)} in {month}?"})
        return json.dumps({"subtasks": subtasks})

    def _followup(self, prompt: str) -> str:
        question = re.search(r"^Question: (.+)$", prompt, re.MULTILINE).group(1)
        request = self._request(prompt).lower()
        options = re.findall(r"\b[A-Z]{3}\b", question)
        home = next((code for city, code in CITY_CURRENCY.items() if f"live in {city}" in request), None)
        if home in options:
            return home
        return "I don't know. Please make a reasonable assumption and say which one you used."

    def _summarize(self, prompt: str) -> str:
        results = re.findall(r"^- (\w+): (.+)$", prompt, re.MULTILINE)
        if not results:
            return "None of my partner agents could help."
        return "Here's your trip brief: " + "; ".join(text.rstrip(".") for _, text in results) + "."


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or DEFAULT_MODELS["anthropic"]
        self.name = f"anthropic:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=16000, system=system, messages=[{"role": "user", "content": prompt}])
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
            model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from ``LLM_PROVIDER`` (default: mock)."""
    settings = settings or load_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockLLM()
