"""Short-term memory: the last few turns, kept under a token budget.

When the buffer is full, the oldest messages are evicted and handed back to the
caller, which summarises them so the gist survives even though the words don't.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Rough token count (~1.3 tokens per English word). Good enough for budgeting."""
    return math.ceil(len(text.split()) * 1.3)


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant"
    text: str

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def render(self) -> str:
        return f"{self.role}: {self.text}"


class ShortTermMemory:
    def __init__(self, max_tokens: int = 80) -> None:
        self.max_tokens = max_tokens
        self.messages: deque[Message] = deque()

    @property
    def tokens(self) -> int:
        return sum(m.tokens for m in self.messages)

    def add(self, role: str, text: str) -> list[Message]:
        """Append a message; return the messages evicted to get back under budget."""
        self.messages.append(Message(role, text))
        evicted: list[Message] = []
        while self.tokens > self.max_tokens and len(self.messages) > 1:
            evicted.append(self.messages.popleft())
        return evicted

    def render(self) -> str:
        return "\n".join(m.render() for m in self.messages)
