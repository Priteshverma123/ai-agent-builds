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
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"          # mock | anthropic | openai
    llm_model: str | None = None        # None -> DEFAULT_MODELS[provider]
    max_steps: int = 25                 # observe -> act iterations before the agent gives up
    site_dir: Path = PROJECT_ROOT / "examples" / "site"  # catalog + templates for the simulated shop


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``); unset keys keep defaults."""
    env = os.environ if env is None else env
    d = Settings()
    return Settings(
        llm_provider=env.get("LLM_PROVIDER", d.llm_provider).strip().lower() or d.llm_provider,
        llm_model=env.get("LLM_MODEL") or None,
        max_steps=int(env.get("AGENT_MAX_STEPS", d.max_steps)),
        site_dir=Path(env.get("SHOP_SITE_DIR") or d.site_dir),
    )
