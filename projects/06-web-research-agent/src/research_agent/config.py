"""Typed settings loaded from the environment: the single source of truth for configuration.

Every knob the code reads lives here, so `.env.example`, the Dockerfile and the tests agree on
names and defaults. Settings are read at call time (not import time), so a test or a shell can
change an env var and the next `Settings.from_env()` sees it. Unset or empty = the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # agent -> llm -> config: import lazily to avoid a cycle
    from .agent import ResearchConfig

Provider = Literal["mock", "anthropic", "openai"]
PROVIDERS: tuple[str, ...] = ("mock", "anthropic", "openai")
DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@dataclass(frozen=True)
class Settings:
    llm_provider: Provider = "mock"  # LLM_PROVIDER: mock (offline) | anthropic | openai
    llm_model: str | None = None  # LLM_MODEL: None = the provider default in DEFAULT_MODELS
    web_dir: Path = EXAMPLES_DIR / "web"  # RESEARCH_WEB_DIR: folder of .txt pages that stands in for the web
    results_per_query: int = 2  # RESEARCH_RESULTS_PER_QUERY: search results considered per planned query
    max_fetches: int = 5  # RESEARCH_MAX_FETCHES: page fetches allowed per question (the budget)

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai.")
        return cls(
            llm_provider=provider,  # type: ignore[arg-type]
            llm_model=os.getenv("LLM_MODEL", "").strip() or None,
            web_dir=_path("RESEARCH_WEB_DIR", EXAMPLES_DIR / "web"),
            results_per_query=_positive_int("RESEARCH_RESULTS_PER_QUERY", 2),
            max_fetches=_positive_int("RESEARCH_MAX_FETCHES", 5),
        )

    def research_config(self) -> ResearchConfig:
        """The agent's loop budget, built from these settings."""
        from .agent import ResearchConfig

        return ResearchConfig(results_per_query=self.results_per_query, max_fetches=self.max_fetches)

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


def _path(env: str, default: Path) -> Path:
    raw = os.getenv(env, "").strip()
    return Path(raw) if raw else default
