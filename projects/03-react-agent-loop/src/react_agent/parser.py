"""Parse one model reply in the ReAct text format.

The model must answer in exactly one of two shapes:

    Thought: <reasoning>              Thought: <reasoning>
    Action: <tool>[<input>]           Final Answer: <answer>
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_THOUGHT = re.compile(r"Thought:\s*(.*?)(?=\n\s*(?:Action|Final Answer):|\Z)", re.DOTALL)
_ACTION = re.compile(r"Action:\s*(\w+)\s*\[(.*)\]", re.DOTALL)
_FINAL = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)


class ParseError(ValueError):
    """The reply didn't follow the format. We tell the model and let it try again."""


@dataclass(frozen=True)
class Step:
    thought: str
    action: str | None = None
    action_input: str | None = None
    final_answer: str | None = None


def parse(reply: str) -> Step:
    # Models sometimes keep going and invent their own "Observation:". Only we may write those.
    reply = reply.split("Observation:")[0].strip()
    thought_match = _THOUGHT.search(reply)
    thought = thought_match.group(1).strip() if thought_match else ""

    if final := _FINAL.search(reply):
        return Step(thought, final_answer=final.group(1).strip())
    if action := _ACTION.search(reply):
        return Step(thought, action=action.group(1), action_input=action.group(2).strip())
    raise ParseError("expected 'Action: tool[input]' or 'Final Answer: ...'")
