"""Typed settings loaded from the environment: the single source of truth for configuration.

Read at call time (not import time) so tests and containers can change behaviour with env vars.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_db() -> Path:
    return Path(tempfile.gettempdir()) / "sql_analyst_shop.db"


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                                       # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None                                     # LLM_MODEL: provider model id
    db_path: Path = field(default_factory=_default_db)               # SQL_DB_PATH: where the demo DB is built
    seed_sql: Path = PROJECT_ROOT / "examples" / "shop.sql"          # SQL_SEED: schema + rows for the demo DB
    questions: Path = PROJECT_ROOT / "examples" / "questions.txt"    # SQL_QUESTIONS: demo questions, one per line
    max_attempts: int = 3                                            # SQL_MAX_ATTEMPTS: draft + repair attempts
    max_rows: int = 200                                              # SQL_MAX_ROWS: LIMIT the guard enforces
    timeout_ms: int = 2000                                           # SQL_TIMEOUT_MS: per-query time budget

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        default = cls()
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            db_path=Path(env["SQL_DB_PATH"]) if env.get("SQL_DB_PATH") else default.db_path,
            seed_sql=Path(env["SQL_SEED"]) if env.get("SQL_SEED") else default.seed_sql,
            questions=Path(env["SQL_QUESTIONS"]) if env.get("SQL_QUESTIONS") else default.questions,
            max_attempts=int(env.get("SQL_MAX_ATTEMPTS") or 3),
            max_rows=int(env.get("SQL_MAX_ROWS") or 200),
            timeout_ms=int(env.get("SQL_TIMEOUT_MS") or 2000),
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
