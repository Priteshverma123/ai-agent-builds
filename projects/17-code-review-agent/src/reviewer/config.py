"""Typed settings loaded from the environment: the single source of truth for configuration.

Read at call time (not import time) so CI jobs and tests can change behaviour with env vars.
CLI flags always win over these defaults.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRUE = {"1", "true", "yes", "on"}
FORMATS = ("text", "markdown", "json")
SEVERITIES = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                                  # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None                                # LLM_MODEL: provider model id
    diff: str = str(PROJECT_ROOT / "examples" / "change.diff")  # REVIEW_DIFF: unified diff file, or - for stdin
    base: Path = PROJECT_ROOT / "examples" / "base"             # REVIEW_BASE: repo checkout before the change
    output_format: str = "text"                                 # REVIEW_FORMAT: text | markdown | json
    fail_on: str | None = None                                  # REVIEW_FAIL_ON: low | medium | high | critical
    static_only: bool = False                                   # REVIEW_STATIC_ONLY: skip the LLM pass

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        default = cls()
        fmt = (env.get("REVIEW_FORMAT") or "text").strip().lower()
        fail_on = (env.get("REVIEW_FAIL_ON") or "").strip().lower() or None
        if fmt not in FORMATS:
            raise ValueError(f"REVIEW_FORMAT must be one of {FORMATS}, got {fmt!r}")
        if fail_on is not None and fail_on not in SEVERITIES:
            raise ValueError(f"REVIEW_FAIL_ON must be one of {SEVERITIES}, got {fail_on!r}")
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            diff=env.get("REVIEW_DIFF") or default.diff,
            base=Path(env["REVIEW_BASE"]) if env.get("REVIEW_BASE") else default.base,
            output_format=fmt,
            fail_on=fail_on,
            static_only=env.get("REVIEW_STATIC_ONLY", "").strip().lower() in TRUE,
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
