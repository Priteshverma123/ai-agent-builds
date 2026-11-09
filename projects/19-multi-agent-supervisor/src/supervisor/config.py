"""Typed settings loaded from the environment: the single source of truth for configuration.

Every knob the code reads lives here, with the same safe defaults the demo uses. Nothing else in
the package calls ``os.getenv``; it asks :func:`load_settings` instead.
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
    max_steps: int = 8                  # supervisor step budget
    max_coder_visits: int = 3           # how many times the coder may be called
    review_timeout_s: float = 2.0       # hard limit for running candidate code
    kb_dir: Path = PROJECT_ROOT / "examples" / "kb"

    @property
    def use_mock(self) -> bool:
        return self.llm_provider in ("", "mock")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``); unset keys keep defaults."""
    env = os.environ if env is None else env
    defaults = Settings()
    return Settings(
        llm_provider=env.get("LLM_PROVIDER", defaults.llm_provider).strip().lower(),
        llm_model=env.get("LLM_MODEL") or None,
        max_steps=int(env.get("SUPERVISOR_MAX_STEPS", defaults.max_steps)),
        max_coder_visits=int(env.get("SUPERVISOR_MAX_CODER_VISITS", defaults.max_coder_visits)),
        review_timeout_s=float(env.get("REVIEW_TIMEOUT_S", defaults.review_timeout_s)),
        kb_dir=Path(env.get("KB_DIR") or defaults.kb_dir),
    )
