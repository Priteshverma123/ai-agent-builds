"""Command-line entry: plan a trip, hit a sold-out hotel, re-plan, and finish the job.

    planner-executor                         # goal from examples/goal.txt
    planner-executor --goal "Book a 2-night trip from London to Lisbon ..."
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import PlanExecuteAgent
from .config import Settings
from .llm import make_llm
from .tools import TravelWorld
from .trace import Trace


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Planner-executor agent on a simulated travel-booking world.")
    parser.add_argument("--goal", help="goal text (default: the contents of --goal-file)")
    parser.add_argument("--goal-file", type=Path, default=settings.goal_file, help="file holding the goal")
    args = parser.parse_args(argv)
    goal = args.goal or args.goal_file.read_text(encoding="utf-8").strip()

    world = TravelWorld()
    agent = PlanExecuteAgent(make_llm(settings), world.tools(), max_replans=settings.max_replans, trace=Trace())
    result = agent.run(goal)
    if result.status == "done":
        print(f"\nBooked: {'; '.join(b['what'] for b in world.bookings)}  |  total {world.spend} EUR")
    return 0 if result.status == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
