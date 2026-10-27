"""CLI: run the ReAct agent on the demo questions (or your own) and print every step.

Used by `demo.py`, `python -m react_agent` and the `react-agent` console script.

    python demo.py
    python demo.py "How much taller is Mount Everest than K2, in metres?"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import ReActAgent, Result, TraceStep
from .config import Settings
from .llm import make_llm
from .tools import default_tools
from .ui import banner, box

QUESTIONS = Path(__file__).resolve().parents[2] / "examples" / "questions.txt"


def step_rows(step: TraceStep) -> list[tuple[str, str]]:
    rows = [(f"step {step.number}", ""), ("  thought", step.thought)]
    if step.final_answer is not None:
        rows.append(("  answer", step.final_answer))
    else:
        if step.action:
            rows.append(("  action", f"{step.action}[{step.action_input}]"))
        rows.append(("  observe", step.observation or ""))
    return rows


def summary(result: Result, max_steps: int) -> str:
    if result.stop_reason == "answered":
        return f"answered in {len(result.steps)} step(s)"
    return f"STOPPED: hit the {max_steps}-step limit without an answer"


def main(argv: list[str] | None = None) -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="A ReAct agent with a readable trace.")
    parser.add_argument("question", nargs="?", help="ask your own question instead of the demo set")
    parser.add_argument("--max-steps", type=int, default=settings.max_steps, help="step limit (env: REACT_MAX_STEPS)")
    args = parser.parse_args(argv)

    llm = make_llm(settings)
    agent = ReActAgent(llm, default_tools(), max_steps=args.max_steps)
    print(banner(f"03 - ReAct agent loop | model: {type(llm).__name__} | tools: {', '.join(agent.tools)}"))

    questions = [args.question] if args.question else [
        q.strip() for q in QUESTIONS.read_text(encoding="utf-8").splitlines() if q.strip()
    ]
    for number, question in enumerate(questions, start=1):
        result = agent.run(question)
        rows = [("question", question)]
        for step in result.steps:
            rows += step_rows(step)
        rows.append(("result", summary(result, args.max_steps)))
        print(box(f"Q{number}", rows))


if __name__ == "__main__":
    main()
