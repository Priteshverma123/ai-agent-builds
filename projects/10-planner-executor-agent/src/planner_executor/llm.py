"""LLM clients. ``MockPlannerLLM`` is deterministic and used by default and in tests.

The planner prompt is a JSON document (goal, tools, and on re-plan: the current plan,
completed outputs and the failure). The mock reads that JSON and applies two rules a
human travel agent would use:
  1. First plan: search -> book flight -> search -> book hotel -> send itinerary.
  2. A booking failed as unavailable: search again excluding that option, rebook,
     and repoint every later step at the new booking. Anything else: abort.
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


class MockPlannerLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        request = json.loads(prompt)
        plan = self._replan(request) if request.get("failure") else self._first_plan(request["goal"])
        return json.dumps(plan)

    @staticmethod
    def _first_plan(goal: str) -> dict:
        origin, destination = re.search(r"from (\w+) to (\w+)", goal).groups()
        date = re.search(r"\d{4}-\d{2}-\d{2}", goal).group(0)
        nights = int(re.search(r"(\d+)-night", goal).group(1))
        email = re.search(r"[\w.+-]+@[\w.-]+", goal).group(0)
        return {"steps": [
            {"id": "s1", "tool": "search_flights", "args": {"origin": origin, "destination": destination, "date": date},
             "why": "find flights"},
            {"id": "s2", "tool": "book_flight", "args": {"flight_id": "$s1.0.id"}, "why": "cheapest flight"},
            {"id": "s3", "tool": "search_hotels", "args": {"city": destination, "check_in": date, "nights": nights},
             "why": "find hotels"},
            {"id": "s4", "tool": "book_hotel", "args": {"hotel_id": "$s3.0.id", "nights": nights}, "why": "cheapest hotel"},
            {"id": "s5", "tool": "send_itinerary", "args": {"to": email, "confirmations": ["$s2.confirmation", "$s4.confirmation"]},
             "why": "email it"},
        ]}

    @staticmethod
    def _replan(request: dict) -> dict:
        failure, steps = request["failure"], request["current_plan"]
        unavailable = re.search(r"sold out|unavailable|no seats", failure["error"])
        source = re.match(r"^\$(\w+)\.0\.id$", next((str(v) for v in failure["args"].values() if str(v).startswith("$")), ""))
        if not (failure["tool"].startswith("book_") and unavailable and source):
            return {"abort": f"cannot recover from: {failure['error']}"}

        suffix = "bcdefgh"[request["version"] - 1]
        search = next(s for s in steps if s["id"] == source.group(1))
        failed_option = failure["resolved_args"][next(k for k, v in failure["args"].items() if str(v).startswith("$"))]
        new_search_id, new_book_id = f"{search['id']}{suffix}", f"{failure['step']}{suffix}"
        exclude = [*search["args"].get("exclude", []), failed_option]

        def repoint(value):
            if isinstance(value, list):
                return [repoint(v) for v in value]
            return value.replace(f"${failure['step']}.", f"${new_book_id}.") if isinstance(value, str) else value

        new_steps = []
        for step in steps:
            if step["id"] == failure["step"]:
                new_steps.append({"id": new_search_id, "tool": search["tool"], "args": {**search["args"], "exclude": exclude},
                                  "why": f"search again without {failed_option}"})
                book_args = {k: (f"${new_search_id}.0.id" if str(v).startswith("$") else v) for k, v in step["args"].items()}
                new_steps.append({"id": new_book_id, "tool": step["tool"], "args": book_args, "why": "book the next-best option"})
            else:
                new_steps.append({**step, "args": {k: repoint(v) for k, v in step["args"].items()}})
        return {"steps": new_steps}


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
    return MockPlannerLLM()
