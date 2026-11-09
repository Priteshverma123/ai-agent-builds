"""Typed settings loaded from environment variables: the single source of truth.

Every knob the project reads lives here, with a safe default, so ``.env.example``,
the CLI and the Dockerfile all describe the same thing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"  # mock | anthropic | openai
    llm_model: str | None = None  # None = the provider's default model
    max_replans: int = 2  # how many times the planner may repair a failed plan
    goal_file: Path = EXAMPLES / "goal.txt"  # the demo goal

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            llm_provider=env.get("LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("LLM_MODEL") or None,
            max_replans=int(env.get("AGENT_MAX_REPLANS", "2")),
            goal_file=Path(env.get("AGENT_GOAL_FILE", str(EXAMPLES / "goal.txt"))),
        )
