"""Typed settings loaded from the environment: the single source of truth for configuration.

Read at call time (not import time) so tests and containers can change behaviour with env vars.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                                   # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None                                 # LLM_MODEL: provider model id
    out_dir: Path = PROJECT_ROOT / "out"                         # TRACE_OUT_DIR: trace.jsonl + trace.html
    questions: Path = PROJECT_ROOT / "examples" / "questions.txt"  # TRACE_QUESTIONS: one question per line
    real_clock: bool = False                                     # TRACE_REAL_CLOCK: wall time instead of sim time
    max_steps: int = 6                                           # AGENT_MAX_STEPS: steps per run
    tool_retries: int = 1                                        # AGENT_TOOL_RETRIES: retries after a tool error

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        default = cls()
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            out_dir=Path(env["TRACE_OUT_DIR"]) if env.get("TRACE_OUT_DIR") else default.out_dir,
            questions=Path(env["TRACE_QUESTIONS"]) if env.get("TRACE_QUESTIONS") else default.questions,
            real_clock=env.get("TRACE_REAL_CLOCK", "").strip().lower() in TRUE,
            max_steps=int(env.get("AGENT_MAX_STEPS") or 6),
            tool_retries=int(env.get("AGENT_TOOL_RETRIES") or 1),
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
