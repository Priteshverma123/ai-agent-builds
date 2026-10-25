"""A chat session = memory + an LLM. One method: send()."""

from __future__ import annotations

from dataclasses import dataclass

from .llm import LLM
from .memory import ConversationMemory, Window


@dataclass
class Turn:
    user: str
    reply: str
    window: Window  # exactly what the model saw when it wrote `reply`


class ChatSession:
    def __init__(self, llm: LLM, memory: ConversationMemory) -> None:
        self.llm = llm
        self.memory = memory

    def send(self, text: str) -> Turn:
        self.memory.add("user", text)
        window = self.memory.window()
        messages = [m.as_dict() for m in window.messages]
        reply = self.llm.complete(self.memory.system_prompt, messages)
        self.memory.add("assistant", reply)
        return Turn(user=text, reply=reply, window=window)
