"""CLI: show the tool schemas, then answer each demo question with a full trace.

Used by `demo.py`, `python -m toolcall` and the `toolcall` console script.

    python demo.py                               # the demo questions
    python demo.py "Convert 99 GBP to INR"       # your own question
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .agent import run
from .config import Settings
from .demo_tools import registry
from .llm import LLM, make_llm
from .tools import ToolCall, ToolResult
from .ui import banner, box

QUESTIONS = Path(__file__).resolve().parents[2] / "examples" / "questions.txt"


def signature(schema: dict[str, Any]) -> str:
    params = schema["parameters"]["properties"]
    return "(" + ", ".join(f"{name}: {p['type']}" for name, p in params.items()) + ")"


def show_tools() -> None:
    schemas = registry.schemas()
    rows = [(s["name"], f"{signature(s)}  {s['description']}") for s in schemas]
    print(box("tools the model can see (it never sees our Python code)", rows))
    print("Full JSON schema for one of them, exactly as sent to the model:")
    print(json.dumps(schemas[0], indent=2), "\n")


def ask(llm: LLM, number: int, question: str, max_rounds: int = 5) -> None:
    rows: list[tuple[str, str]] = [("user", question)]

    def on_event(kind: str, payload: Any) -> None:
        if kind == "text" and payload:
            rows.append(("model", str(payload)))
        elif kind == "call" and isinstance(payload, ToolCall):
            rows.append(("model ->", f"{payload.name}({json.dumps(payload.arguments)})"))
        elif kind == "result" and isinstance(payload, ToolResult):
            rows.append(("tool  <-" if payload.ok else "error <-", payload.content))
        elif kind == "answer":
            rows.append(("answer", str(payload)))

    result = run(question, llm, registry, max_rounds=max_rounds, on_event=on_event)
    print(box(f"Q{number} | {result.rounds} model call(s)", rows))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Function calling with no framework.")
    parser.add_argument("question", nargs="?", help="ask your own question instead of the demo set")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    llm = make_llm(settings)
    print(banner(f"02 - Tool calling from scratch | model: {type(llm).__name__}"))
    show_tools()
    questions = [args.question] if args.question else [
        q.strip() for q in QUESTIONS.read_text(encoding="utf-8").splitlines() if q.strip()
    ]
    for number, question in enumerate(questions, start=1):
        ask(llm, number, question, settings.max_rounds)


if __name__ == "__main__":
    main()
