"""LLM backends: complete(system, messages) -> str. MockLLM is the offline default."""

from __future__ import annotations

import re
from typing import Protocol

from .config import DEFAULT_MODELS, Settings

ChatMessage = dict[str, str]

# Real models are told to stop *before* writing an Observation, so they can't invent one.
STOP_SEQUENCES = ["\nObservation:"]


class LLM(Protocol):
    def complete(self, system: str, messages: list[ChatMessage]) -> str: ...


# --- Offline backends ------------------------------------------------------------

_ENTITY = re.compile(r"\b[A-Z][\w]*(?:\s+[A-Z][\w]*)*")
_QUESTION_WORDS = {"How", "What", "Who", "When", "Where", "Which", "Why", "Is", "Are", "Did", "Does"}
_NUMBER = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{2,}\b")
_PREVIOUS_ACTION = re.compile(r"Action:\s*(\w+)\[(.*)\]")


class MockLLM:
    """A rule-based ReAct policy. It reads the transcript like a model would:

    1. Find the topics named in the question (capitalised phrases).
    2. Search each topic it hasn't searched yet.
    3. If the question asks "how many/much" and two numbers were found, use the calculator.
    4. Otherwise answer from what it observed -- or admit it doesn't know.

    It never peeks at the knowledge base; everything it knows came from Observations.
    """

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        question = messages[0]["content"].removeprefix("Question: ")
        actions = [m for a in messages if a["role"] == "assistant" for m in _PREVIOUS_ACTION.findall(a["content"])]
        observations = [m["content"].removeprefix("Observation: ") for m in messages[1:] if m["role"] == "user"]
        searched = {arg for tool, arg in actions if tool == "search"}

        missing = [o for o in observations if o.startswith("No results")]
        if missing:
            return f"Thought: The search found nothing. I should not guess.\nFinal Answer: I couldn't find that. {missing[0]}"

        for topic in self._topics(question):
            if topic not in searched:
                return f"Thought: I need facts about {topic}.\nAction: search[{topic}]"

        numbers = [found[0] for o in observations if (found := _NUMBER.findall(o))]
        wants_math = re.search(r"\bhow (?:many|much)\b", question, re.IGNORECASE)
        used_calculator = any(tool == "calculator" for tool, _ in actions)

        if wants_math and len(numbers) >= 2 and not used_calculator:
            big, small = sorted(numbers[:2], key=lambda n: int(n.replace(",", "")), reverse=True)
            return (
                f"Thought: I found {numbers[0]} and {numbers[1]}. The difference needs exact math.\n"
                f"Action: calculator[{big} - {small}]"
            )
        if used_calculator:
            unit = next((u for u in ("years", "metres", "kilometres") if u in question), "")
            return f"Thought: The calculator gave me the difference.\nFinal Answer: {observations[-1]} {unit}".rstrip()
        answer = re.sub(r"^\[[^\]]*\]\s*", "", observations[-1])  # drop the "[Article title]" tag
        return f"Thought: The observation answers the question.\nFinal Answer: {answer}"

    @staticmethod
    def _topics(question: str) -> list[str]:
        topics = []
        for phrase in _ENTITY.findall(question):
            words = phrase.split()
            while words and words[0] in _QUESTION_WORDS:
                words.pop(0)
            if words:
                topics.append(" ".join(words))
        return topics


class ScriptedLLM:
    """Replays fixed replies in order. Perfect for testing how the loop handles bad behaviour."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]  # repeat the last one forever
        self.calls += 1
        return reply


# --- Real providers (optional) ---------------------------------------------------


class AnthropicLLM:
    """Claude via the official SDK: `pip install anthropic`, set ANTHROPIC_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODELS["anthropic"]

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=messages,
            stop_sequences=STOP_SEQUENCES,
            betas=["server-side-fallback-2026-07-01"],  # retry on a fallback model if a classifier declines
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            return "Thought: I can't help with this.\nFinal Answer: [the model declined to answer]"
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
            stop=STOP_SEQUENCES,
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
