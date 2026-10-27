"""The ReAct loop: Thought -> Action -> Observation, repeated until a Final Answer or a limit.

ReAct ("Reason + Act", Yao et al., 2022) interleaves reasoning text with tool use, so the
model can plan its next step from what it just observed. The loop below is the whole idea.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from .llm import LLM
from .parser import ParseError, parse
from .tools import Tool

MAX_OBSERVATION_CHARS = 400

SYSTEM_TEMPLATE = """You answer questions by reasoning step by step and using tools.

Tools:
{tools}

Reply in exactly one of these two formats, then stop:

Thought: <what you know so far and what to do next>
Action: <tool name>[<tool input>]

Thought: <why you can now answer>
Final Answer: <the answer>

After each Action you will receive an "Observation:" with the tool's output.
Never write an Observation yourself. Use the calculator for any arithmetic."""


@dataclass
class TraceStep:
    number: int
    thought: str
    action: str | None = None
    action_input: str | None = None
    observation: str | None = None
    final_answer: str | None = None


@dataclass
class Result:
    answer: str | None
    stop_reason: Literal["answered", "max_steps"]
    steps: list[TraceStep] = field(default_factory=list)


class ReActAgent:
    def __init__(self, llm: LLM, tools: dict[str, Tool], max_steps: int = 6) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        tool_lines = "\n".join(f"- {t.name}: {t.description}" for t in tools.values())
        self.system = SYSTEM_TEMPLATE.format(tools=tool_lines)

    def run(self, question: str, on_step: Callable[[TraceStep], None] | None = None) -> Result:
        messages = [{"role": "user", "content": f"Question: {question}"}]
        steps: list[TraceStep] = []
        seen_actions: set[tuple[str, str]] = set()

        for number in range(1, self.max_steps + 1):
            reply = self.llm.complete(self.system, messages)          # Thought + Action
            messages.append({"role": "assistant", "content": reply})
            step = self._step(number, reply, seen_actions)            # run the Action
            steps.append(step)
            if on_step:
                on_step(step)
            if step.final_answer is not None:
                return Result(step.final_answer, "answered", steps)
            messages.append({"role": "user", "content": f"Observation: {step.observation}"})

        return Result(None, "max_steps", steps)  # out of budget: never loop forever

    def _step(self, number: int, reply: str, seen: set[tuple[str, str]]) -> TraceStep:
        try:
            parsed = parse(reply)
        except ParseError as exc:  # tell the model what went wrong; it usually fixes itself
            return TraceStep(number, "(unparseable reply)", observation=f"Format error: {exc}.")
        step = TraceStep(number, parsed.thought, parsed.action, parsed.action_input, final_answer=parsed.final_answer)
        if parsed.final_answer is None:
            step.observation = self._act(parsed.action or "", parsed.action_input or "", seen)
        return step

    def _act(self, name: str, tool_input: str, seen: set[tuple[str, str]]) -> str:
        """Run one tool. Every failure becomes an observation the model can learn from."""
        if (name, tool_input) in seen:
            return "You already ran this exact action. Use that observation or try something different."
        seen.add((name, tool_input))
        tool = self.tools.get(name)
        if tool is None:
            return f"Unknown tool '{name}'. Available tools: {', '.join(self.tools)}."
        output = tool.run(tool_input)
        if len(output) > MAX_OBSERVATION_CHARS:  # long observations eat the context window
            output = output[:MAX_OBSERVATION_CHARS] + " ...[truncated]"
        return output
