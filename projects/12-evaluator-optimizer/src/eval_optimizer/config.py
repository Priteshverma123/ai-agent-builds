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
    llm_provider: str = "mock"  # mock | anthropic | openai (writer and judge)
    llm_model: str | None = None  # None = the provider's default model
    target: float = 90.0  # stop when the rubric total reaches this (0-100)
    max_iterations: int = 6  # hard budget of drafts
    patience: int = 2  # plateau: rounds without a gain of min_delta
    min_delta: float = 1.0
    fixes_per_round: int = 2  # how many top issues the writer gets per revision
    brief_file: Path = EXAMPLES / "brief.json"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            llm_provider=env.get("LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("LLM_MODEL") or None,
            target=float(env.get("OPT_TARGET", "90")),
            max_iterations=int(env.get("OPT_MAX_ITERATIONS", "6")),
            patience=int(env.get("OPT_PATIENCE", "2")),
            min_delta=float(env.get("OPT_MIN_DELTA", "1.0")),
            fixes_per_round=int(env.get("OPT_FIXES_PER_ROUND", "2")),
            brief_file=Path(env.get("OPT_BRIEF_FILE", str(EXAMPLES / "brief.json"))),
        )
