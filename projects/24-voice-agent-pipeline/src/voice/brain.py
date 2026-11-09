"""Thinking: a *streaming* language model. Voice agents live or die by time-to-first-token.

``MockVoiceLLM`` simulates a model on the virtual clock: a time-to-first-token (TTFT), then one
token every ``token_ms``. Questions that need a tool (the weather) take much longer to start,
which is what the filler-phrase policy is for. ``ProviderStreamer`` puts a real model behind the
same interface (``LLM_PROVIDER=anthropic|openai``).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from .clock import Clock
from .config import Settings, load_settings

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}
SYSTEM_PROMPT = ("You are a friendly voice assistant for a small bookshop. Answer in one to three short, "
                 "spoken-style sentences. No lists, no markdown.")

History = list[tuple[str, str]]  # (role, text)


class StreamingLLM(Protocol):
    name: str

    def stream(self, history: History) -> AsyncIterator[str]: ...


_REPLIES = [
    ("hour", 0, "Sure! We're open from nine to six, Monday to Saturday. On public holidays we close at two, "
                "and the cafe upstairs keeps its own hours, so check the board by the stairs when you arrive."),
    ("sunday", 0, "On Sundays we're closed, sorry about that."),
    ("weather", 700, "Tomorrow looks sunny, with a high of twenty-four degrees."),
]


class MockVoiceLLM:
    """Keyword-routed replies streamed word by word on the clock. ``tool_ms`` models a tool call."""

    name = "mock-voice-llm"

    def __init__(self, clock: Clock, ttft_ms: float = 250, token_ms: float = 30) -> None:
        self.clock = clock
        self.ttft_ms = ttft_ms
        self.token_ms = token_ms

    async def stream(self, history: History) -> AsyncIterator[str]:
        user = history[-1][1].lower()
        tool_ms, reply = next(((ms, text) for key, ms, text in _REPLIES if key in user),
                              (0, "Sorry, I didn't catch that. Could you say it again?"))
        await self.clock.sleep(self.ttft_ms + tool_ms)
        for i, word in enumerate(reply.split(" ")):
            if i:
                await self.clock.sleep(self.token_ms)
            yield word + " "


class ProviderStreamer:
    """A real model. For simplicity it fetches the full reply, then streams it word by word;
    swap in the SDK's streaming API to get true token-level latency."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {provider!r}")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.name = f"{provider}:{self.model}"

    def _complete(self, history: History) -> str:
        messages = [{"role": r, "content": t} for r, t in history]
        if self.provider == "anthropic":
            import anthropic  # pip install anthropic

            response = anthropic.Anthropic().messages.create(
                model=self.model, max_tokens=16000, system=SYSTEM_PROMPT, messages=messages)
            return "".join(block.text for block in response.content if block.type == "text")
        from openai import OpenAI  # pip install openai

        response = OpenAI().chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages])
        return response.choices[0].message.content or ""

    async def stream(self, history: History) -> AsyncIterator[str]:
        for word in (await asyncio.to_thread(self._complete, history)).split():
            yield word + " "


def provider_from_env(settings: Settings | None = None) -> ProviderStreamer | None:
    """A real streaming model if ``LLM_PROVIDER`` asks for one, otherwise ``None`` (use the mock)."""
    settings = settings or load_settings()
    if settings.use_mock:
        return None
    return ProviderStreamer(settings.llm_provider, settings.llm_model)
