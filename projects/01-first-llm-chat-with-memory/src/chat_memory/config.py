"""Typed settings loaded from the environment: the single source of truth for configuration.

Every knob the code reads lives here, so `.env.example`, the Dockerfile and the tests agree on
names and defaults. Settings are read at call time (not import time), so a test or a shell can
change an env var and the next `Settings.from_env()` sees it. Unset or empty = the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Provider = Literal["mock", "anthropic", "openai"]
PROVIDERS: tuple[str, ...] = ("mock", "anthropic", "openai")
DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


@dataclass(frozen=True)
class Settings:
    llm_provider: Provider = "mock"  # LLM_PROVIDER: mock (offline) | anthropic | openai
    llm_model: str | None = None  # LLM_MODEL: None = the provider default in DEFAULT_MODELS
    chat_budget: int = 140  # CHAT_BUDGET: context budget in tokens when --budget is not given

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai.")
        return cls(
            llm_provider=provider,  # type: ignore[arg-type]
            llm_model=os.getenv("LLM_MODEL", "").strip() or None,
            chat_budget=_positive_int("CHAT_BUDGET", 140),
        )

    def model_for(self, provider: str) -> str:
        """The model to use: LLM_MODEL if set, else the provider's default."""
        return self.llm_model or DEFAULT_MODELS[provider]


def _positive_int(env: str, default: int) -> int:
    raw = os.getenv(env, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"{env} must be a positive integer, got {raw!r}.")
    return int(raw)
