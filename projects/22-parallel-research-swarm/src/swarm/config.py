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
    llm_provider: str = "mock"          # mock | anthropic | openai (planner + extractor)
    llm_model: str | None = None        # None -> the provider's default model
    concurrency: int = 3                # max fetches in flight across the whole swarm
    fetch_timeout_s: float = 0.3        # per-attempt timeout (starts after a slot is acquired)
    fetch_retries: int = 1              # extra attempts for transient failures
    docs_per_worker: int = 3            # top-k search results each worker fetches
    corpus_dir: Path = PROJECT_ROOT / "examples" / "corpus"

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
        concurrency=int(env.get("SWARM_CONCURRENCY", d.concurrency)),
        fetch_timeout_s=float(env.get("FETCH_TIMEOUT_S", d.fetch_timeout_s)),
        fetch_retries=int(env.get("FETCH_RETRIES", d.fetch_retries)),
        docs_per_worker=int(env.get("DOCS_PER_WORKER", d.docs_per_worker)),
        corpus_dir=Path(env.get("CORPUS_DIR") or d.corpus_dir),
    )
