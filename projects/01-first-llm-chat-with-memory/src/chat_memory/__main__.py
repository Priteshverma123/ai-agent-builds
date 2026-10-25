"""CLI: replay a scripted conversation (default) or chat interactively (--chat).

    python demo.py                      # scripted demo with a tiny budget
    python demo.py --chat --budget 200  # talk to it yourself
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .chat import ChatSession, Turn
from .llm import make_llm
from .memory import ConversationMemory
from .ui import banner, box, meter

SYSTEM_PROMPT = "You are a friendly assistant. Keep answers short."
DEFAULT_SCRIPT = Path(__file__).resolve().parents[2] / "examples" / "demo_conversation.txt"


def render(number: int, turn: Turn, already_dropped: int) -> str:
    """One box per turn. `already_dropped` lets us show only what was lost *this* turn."""
    window = turn.window
    rows = [
        ("you", turn.user),
        ("bot", turn.reply),
        (
            "ctx",
            f"{meter(window.tokens_used, window.budget)} {window.tokens_used}/{window.budget} tokens"
            f" | {len(window.messages)} msgs sent | {len(window.dropped)} dropped",
        ),
    ]
    for message in window.dropped[already_dropped:]:
        if message.role == "user":
            rows.append(("lost", f'fell out of the window: "{message.content}"'))
    return box(f"turn {number}", rows)


def play(session: ChatSession, number: int, text: str, previous: Turn | None) -> Turn:
    """Send one message and print its box. Returns the turn so the caller can chain it."""
    already_dropped = len(previous.window.dropped) if previous else 0
    turn = session.send(text)
    print(render(number, turn, already_dropped))
    return turn


def run_script(session: ChatSession, script: Path) -> None:
    lines = [ln.strip() for ln in script.read_text(encoding="utf-8").splitlines()]
    turn = None
    for number, line in enumerate((ln for ln in lines if ln), start=1):
        turn = play(session, number, line, turn)
    if turn:
        print(
            f"\nFull transcript: {len(session.memory.history)} messages. "
            f"On the last turn the model saw only {len(turn.window.messages)}."
        )
    print("Nothing was deleted -- it just didn't fit in the window. That is AI 'forgetting'.")


def run_chat(session: ChatSession, save_to: Path | None) -> None:
    print("Type a message (empty line to quit).")
    number, turn = len(session.memory.history) // 2, None
    while text := input("you > ").strip():
        number += 1
        turn = play(session, number, text, turn)
        if save_to:
            session.memory.save(save_to)


def main() -> None:
    parser = argparse.ArgumentParser(description="A chat CLI with a token-budget memory window.")
    parser.add_argument("--budget", type=int, default=140, help="context budget in tokens")
    parser.add_argument("--chat", action="store_true", help="chat interactively")
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT, help="conversation to replay")
    parser.add_argument("--session", type=Path, help="JSON file to resume from and save to (--chat)")
    args = parser.parse_args()

    if args.session and args.session.exists():
        memory = ConversationMemory.load(args.session)
    else:
        memory = ConversationMemory(SYSTEM_PROMPT, args.budget)
    llm = make_llm()
    session = ChatSession(llm, memory)

    print(banner(f"01 - Chat with memory | model: {type(llm).__name__} | budget: {memory.budget} tokens"))
    if args.chat:
        run_chat(session, args.session)
    else:
        run_script(session, args.script)


if __name__ == "__main__":
    main()
