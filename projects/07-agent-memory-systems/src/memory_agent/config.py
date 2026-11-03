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


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"  # mock | anthropic | openai
    llm_model: str | None = None  # None = the provider's default model
    buffer_tokens: int = 60  # short-term buffer budget used by the CLI/demo
    recall_k: int = 4  # memories recalled per turn
    memory_db: Path | None = None  # None = a fresh temporary SQLite file per run
    examples_dir: Path = PROJECT_ROOT / "examples"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        db = env.get("MEMORY_DB")
        return cls(
            llm_provider=env.get("LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("LLM_MODEL") or None,
            buffer_tokens=int(env.get("MEMORY_BUFFER_TOKENS", "60")),
            recall_k=int(env.get("MEMORY_RECALL_K", "4")),
            memory_db=Path(db) if db else None,
            examples_dir=Path(env.get("EXAMPLES_DIR", str(PROJECT_ROOT / "examples"))),
        )
