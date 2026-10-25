"""Conversation memory with a token-budget window.

An LLM API is stateless: it only knows what you send in *this* request. "Memory" is
just the list of past messages you choose to resend. Context windows are finite (and
every token costs money), so we keep the full transcript but only send the newest
messages that fit in a token budget. Anything older silently falls out -- that is
exactly why chatbots "forget".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from .tokens import MESSAGE_OVERHEAD, count_tokens

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    @property
    def tokens(self) -> int:
        return count_tokens(self.content) + MESSAGE_OVERHEAD

    def as_dict(self) -> dict[str, str]:
        """The provider-neutral shape every chat API accepts."""
        return {"role": self.role, "content": self.content}


@dataclass
class Window:
    """What the model will actually see on the next call."""

    messages: list[Message]
    dropped: list[Message]
    tokens_used: int
    budget: int


@dataclass
class ConversationMemory:
    system_prompt: str
    budget: int
    history: list[Message] = field(default_factory=list)

    @property
    def system_tokens(self) -> int:
        return count_tokens(self.system_prompt) + MESSAGE_OVERHEAD

    def add(self, role: Role, content: str) -> Message:
        message = Message(role, content)
        self.history.append(message)
        return message

    def window(self) -> Window:
        """Pick the newest messages that fit in the budget.

        1. The system prompt is always sent, so we pay for it first.
        2. Walk backwards from the newest message, keeping messages while they fit.
           We stop at the first one that doesn't, so the window stays contiguous
           (skipping a message would leave a confusing gap in the dialogue).
        3. The newest message is always kept, even if it alone is over budget.
        4. Chat APIs expect the conversation to start with a user turn.
        """
        remaining = self.budget - self.system_tokens
        kept: list[Message] = []
        for message in reversed(self.history):
            if kept and message.tokens > remaining:
                break
            kept.append(message)
            remaining -= message.tokens
        kept.reverse()
        while len(kept) > 1 and kept[0].role != "user":
            kept.pop(0)

        dropped = self.history[: len(self.history) - len(kept)]
        used = self.system_tokens + sum(m.tokens for m in kept)
        return Window(messages=kept, dropped=dropped, tokens_used=used, budget=self.budget)

    def save(self, path: Path) -> None:
        """Persist the *full* transcript, so a session survives a restart."""
        data = {
            "system_prompt": self.system_prompt,
            "budget": self.budget,
            "history": [asdict(m) for m in self.history],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ConversationMemory:
        data = json.loads(path.read_text(encoding="utf-8"))
        history = [Message(m["role"], m["content"]) for m in data["history"]]
        return cls(data["system_prompt"], data["budget"], history)
