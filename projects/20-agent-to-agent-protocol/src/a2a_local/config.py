"""Typed settings loaded from the environment: the single source of truth for configuration.

Nothing else in the package calls ``os.getenv``; it asks :func:`load_settings` instead. Defaults are
exactly what the offline demo uses.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"           # mock | anthropic | openai (planner model)
    llm_model: str | None = None         # None -> DEFAULT_MODELS[provider]
    weather_work_seconds: float = 0.4    # simulated latency of the slow weather agent
    max_followups: int = 2               # input-required rounds the planner will answer per task
    host: str = "127.0.0.1"              # bind address for `--serve`
    port: int = 8001                     # port for `--serve`

    @property
    def model(self) -> str | None:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``); unset keys keep defaults."""
    env = os.environ if env is None else env
    d = Settings()
    return Settings(
        llm_provider=env.get("LLM_PROVIDER", d.llm_provider).strip().lower() or d.llm_provider,
        llm_model=env.get("LLM_MODEL") or None,
        weather_work_seconds=float(env.get("WEATHER_WORK_SECONDS", d.weather_work_seconds)),
        max_followups=int(env.get("PLANNER_MAX_FOLLOWUPS", d.max_followups)),
        host=env.get("A2A_HOST") or d.host,
        port=int(env.get("A2A_PORT", d.port)),
    )
