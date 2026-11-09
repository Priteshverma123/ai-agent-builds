"""Typed settings loaded from the environment: the single source of truth for configuration.

Nothing else in the package calls ``os.getenv``; it asks :func:`load_settings` instead. Defaults are
exactly what the offline demo uses.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"          # mock | anthropic | openai
    llm_model: str | None = None        # None -> the provider's default model
    max_rounds: int = 4                 # hard cap on debate rounds
    threshold: float = 0.66             # weighted agreement needed to call consensus
    script_path: Path = PROJECT_ROOT / "examples" / "debates.json"  # MockDebateLLM script + demo questions

    @property
    def use_mock(self) -> bool:
        return self.llm_provider in ("", "mock")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``); unset keys keep defaults."""
    env = os.environ if env is None else env
    d = Settings()
    return Settings(
        llm_provider=env.get("LLM_PROVIDER", d.llm_provider).strip().lower(),
        llm_model=env.get("LLM_MODEL") or None,
        max_rounds=int(env.get("DEBATE_MAX_ROUNDS", d.max_rounds)),
        threshold=float(env.get("CONSENSUS_THRESHOLD", d.threshold)),
        script_path=Path(env.get("DEBATE_SCRIPT") or d.script_path),
    )
