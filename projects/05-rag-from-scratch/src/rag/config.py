"""Typed settings loaded from the environment: the single source of truth for configuration.

Every knob the code reads lives here, so `.env.example`, the Dockerfile and the tests agree on
names and defaults. Settings are read at call time (not import time), so a test or a shell can
change an env var and the next `Settings.from_env()` sees it. Unset or empty = the default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Provider = Literal["mock", "anthropic", "openai"]
PROVIDERS: tuple[str, ...] = ("mock", "anthropic", "openai")
DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}
EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@dataclass(frozen=True)
class Settings:
    llm_provider: Provider = "mock"  # LLM_PROVIDER: mock (offline) | anthropic | openai
    llm_model: str | None = None  # LLM_MODEL: None = the provider default in DEFAULT_MODELS
    docs_dir: Path = EXAMPLES_DIR / "docs"  # RAG_DOCS_DIR: folder of .md files to index
    top_k: int = 3  # RAG_TOP_K: chunks retrieved per question
    chunk_words: int = 40  # RAG_CHUNK_WORDS: max words per chunk
    min_score: float = 0.1  # RAG_MIN_SCORE: cosine similarity floor; below it a chunk is ignored

    @classmethod
    def from_env(cls) -> Settings:
        provider = os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai.")
        return cls(
            llm_provider=provider,  # type: ignore[arg-type]
            llm_model=os.getenv("LLM_MODEL", "").strip() or None,
            docs_dir=_path("RAG_DOCS_DIR", EXAMPLES_DIR / "docs"),
            top_k=_positive_int("RAG_TOP_K", 3),
            chunk_words=_positive_int("RAG_CHUNK_WORDS", 40),
            min_score=_non_negative_float("RAG_MIN_SCORE", 0.1),
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


def _non_negative_float(env: str, default: float) -> float:
    raw = os.getenv(env, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{env} must be a number, got {raw!r}.") from None
    if value < 0:
        raise ValueError(f"{env} must be >= 0, got {raw!r}.")
    return value


def _path(env: str, default: Path) -> Path:
    raw = os.getenv(env, "").strip()
    return Path(raw) if raw else default
