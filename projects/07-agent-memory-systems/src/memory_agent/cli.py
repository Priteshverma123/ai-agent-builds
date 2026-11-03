"""Command-line entry: two chat sessions that share one long-term memory.

    memory-agent                 # fresh, temporary memory database
    memory-agent --db memory.db  # keep the database to inspect it afterwards
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .agent import MemoryAgent
from .config import Settings
from .llm import make_llm
from .store import LongTermMemory
from .trace import Trace


def run_session(db_path: Path, title: str, messages: list[str], trace: Trace, settings: Settings) -> None:
    """One 'day': open the SQLite store, chat through ``messages``, save an episode, close."""
    store = LongTermMemory(db_path)
    agent = MemoryAgent(make_llm(settings), store, buffer_tokens=settings.buffer_tokens,
                        recall_k=settings.recall_k, trace=trace)
    trace.box(title, [f"long-term memories on disk: {len(store.all())}  |  short-term buffer: empty"])
    for text in messages:
        agent.chat(text)
    agent.end_session()
    store.close()


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Agent memory demo: day 1 and day 2 share one SQLite memory.")
    parser.add_argument("--db", type=Path, default=settings.memory_db,
                        help="SQLite file to use (default: $MEMORY_DB or a temp file)")
    parser.add_argument("--sessions", type=Path, default=settings.examples_dir / "sessions.json",
                        help="JSON file with 'day_1' and 'day_2' message lists")
    args = parser.parse_args(argv)
    sessions = json.loads(args.sessions.read_text(encoding="utf-8"))
    trace = Trace()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = args.db or Path(tmp) / "memory.db"
        run_session(db_path, "DAY 1 - new user, empty memory", sessions["day_1"], trace, settings)
        trace.blank()
        run_session(db_path, "DAY 2 - process restarted, same SQLite file", sessions["day_2"], trace, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
