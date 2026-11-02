"""LLM backends: complete(system, messages) -> str. MockLLM is the offline default."""

from __future__ import annotations

import re
from typing import Protocol

from .chunking import split_sentences
from .config import DEFAULT_MODELS, Settings
from .embed import tokenize

ChatMessage = dict[str, str]


class LLM(Protocol):
    def complete(self, system: str, messages: list[ChatMessage]) -> str: ...


# --- The offline mock ------------------------------------------------------------

_SOURCE_LINE = re.compile(r"^\[(\d+)\] \([^)]*\) (.*)$", re.MULTILINE)
_QUESTION_LINE = re.compile(r"^Question: (.*)$", re.MULTILINE)


class MockLLM:
    """An extractive 'model': it quotes the source sentences that best overlap the question
    and cites them. Like a well-behaved real model, it only uses the sources in the prompt
    and says so when they don't contain the answer.
    """

    def __init__(self, min_overlap: int = 2, max_sentences: int = 2) -> None:
        self.min_overlap = min_overlap
        self.max_sentences = max_sentences

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        prompt = messages[-1]["content"]
        question_match = _QUESTION_LINE.search(prompt)
        question_terms = set(tokenize(question_match.group(1) if question_match else ""))

        sentences: dict[str, str] = {}  # sentence -> first source number (overlapping chunks repeat sentences)
        for number, text in _SOURCE_LINE.findall(prompt):
            for sentence in split_sentences(text):
                sentences.setdefault(sentence, number)
        terms = {s: question_terms & set(tokenize(s)) for s in sentences}
        # A matching word that appears in many sentences ("ship") says less than a rare one ("canada").
        spread = {t: sum(t in found for found in terms.values()) for t in question_terms}

        scored = [
            (sum(1 / spread[t] for t in found), sentence)
            for sentence, found in terms.items()
            if len(found) >= self.min_overlap
        ]
        if not scored:
            return "The sources don't contain the answer to that question, so I don't know."
        best = sorted(scored, key=lambda pair: pair[0], reverse=True)[: self.max_sentences]
        return " ".join(f"{sentence} [{sentences[sentence]}]" for _, sentence in best)


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
            betas=["server-side-fallback-2026-07-01"],  # retry on a fallback model if a classifier declines
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
