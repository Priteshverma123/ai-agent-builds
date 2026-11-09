"""Provider adapters. The gateway only knows the `Provider` protocol; MockLLM is the default."""
from __future__ import annotations

import math
import threading
from typing import Protocol

from gateway.domain.errors import ProviderError
from gateway.domain.models import Completion, Message


def estimate_tokens(text: str) -> int:
    """Rough rule of thumb: ~4 characters per token for English text."""
    return max(1, math.ceil(len(text) / 4))


class Provider(Protocol):
    name: str

    def complete(self, model: str, messages: list[Message], max_tokens: int, temperature: float) -> Completion: ...


class MockLLM:
    """Deterministic provider. Same input -> same output, so caching and costs are reproducible.

    `fail_next(n)` makes the next n calls raise ProviderError, `set_down(True)` simulates an outage.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self._down = False
        self._failures_left = 0
        self._lock = threading.Lock()

    def set_down(self, down: bool) -> None:
        with self._lock:
            self._down = down

    def fail_next(self, n: int) -> None:
        with self._lock:
            self._failures_left = n

    def complete(self, model: str, messages: list[Message], max_tokens: int, temperature: float) -> Completion:
        with self._lock:
            self.calls += 1
            if self._down:
                raise ProviderError(f"{self.name}: 503 service unavailable")
            if self._failures_left > 0:
                self._failures_left -= 1
                raise ProviderError(f"{self.name}: 529 overloaded")
        question = messages[-1].content.strip()
        text = self._answer(model, question, max_tokens)
        words = text.split()
        # Honour max_tokens exactly: the budget reservation relies on it.
        while estimate_tokens(" ".join(words)) > max_tokens and len(words) > 1:
            words.pop()
        text = " ".join(words)
        prompt = "\n".join(m.content for m in messages)
        return Completion(text=text, input_tokens=estimate_tokens(prompt), output_tokens=estimate_tokens(text))

    @staticmethod
    def _answer(model: str, question: str, max_tokens: int) -> str:
        if "essay" in question.lower():  # long-form request: fill the whole output allowance
            filler = "Agents need guardrails, budgets and observability before they meet real users."
            return " ".join([f"[{model}]"] + [filler] * (max_tokens * 4 // len(filler) + 1))
        topic = question.rstrip("?.! ").split()[-1].lower() if question.split() else "that"
        if "pro" in model:
            return (f"[{model}] Detailed analysis of '{topic}': first, define the goal; second, list the "
                    f"constraints; third, compare two options and pick the one with the lowest risk.")
        return f"[{model}] Short answer about '{topic}': it limits work per unit of time."
