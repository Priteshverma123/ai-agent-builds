"""A debater: a persona plus a model, producing one validated :class:`Argument` per round."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic import ValidationError

from .llm import LLM, extract_json
from .messages import Argument, Position

SYSTEM_PROMPT = """You are {name}, {persona}, taking part in a structured debate.
Argue from your own expertise. Change your stance only if another agent's claim genuinely
persuades you, and then say which claim in "changed_because". Do not agree just to be agreeable.
Reply with JSON only:
{{"stance": "for" | "against" | "conditional", "confidence": 0.0-1.0,
  "claims": ["topic: claim", ...], "changed_because": "<empty unless you changed stance>"}}"""


@dataclass
class Debater:
    name: str
    persona: str
    llm: LLM
    retries: int = 1

    async def argue(self, question: str, round_no: int, transcript: str) -> Position:
        """One turn. Invalid replies get one corrective retry, then the agent abstains."""
        prompt = f"QUESTION: {question}\nAGENT: {self.name}\nROUND: {round_no}\n"
        prompt += f"\nWHAT THE OTHERS SAID LAST ROUND:\n{transcript}" if transcript else \
            "\nThis is the opening round: give your independent view."
        error = ""
        for _ in range(self.retries + 1):
            reply = await asyncio.to_thread(self.llm.complete, SYSTEM_PROMPT.format(name=self.name, persona=self.persona),
                                            prompt + (f"\n\nYOUR LAST REPLY WAS INVALID: {error}" if error else ""))
            try:
                return Position(agent=self.name, round=round_no, argument=Argument.model_validate(extract_json(reply)))
            except (ValueError, ValidationError) as exc:
                error = str(exc).splitlines()[0]
        return Position(agent=self.name, round=round_no, error=error)


PANEL = {
    "architect": "a principal software architect who likes clean boundaries and ambitious designs",
    "sre": "a site reliability engineer who has been paged at 3am too many times",
    "pm": "a product manager accountable for this quarter's customer commitments",
    "finance": "the finance lead who watches burn rate and cloud spend",
}


def make_panel(llm: LLM) -> list[Debater]:
    return [Debater(name, persona, llm) for name, persona in PANEL.items()]
