"""Typed settings loaded from the environment: the single source of truth for configuration.

Every knob the code reads lives here, so `.env.example`, the CLI and the tests agree on names
and defaults. Settings are read at call time (not import time) so tests can monkeypatch env vars.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("mock", "anthropic", "openai")


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"          # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None        # LLM_MODEL: provider model id (provider default if unset)
    guard_threshold: float = 0.5        # GUARD_THRESHOLD: detector score that counts as an injection
    max_steps: int = 6                  # AGENT_MAX_STEPS: model turns before the agent gives up
    examples_dir: Path = PROJECT_ROOT / "examples"  # EXAMPLES_DIR: fake web, notes, red-team corpus

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            guard_threshold=float(env.get("GUARD_THRESHOLD") or 0.5),
            max_steps=int(env.get("AGENT_MAX_STEPS") or 6),
            examples_dir=Path(env["EXAMPLES_DIR"]) if env.get("EXAMPLES_DIR") else PROJECT_ROOT / "examples",
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
