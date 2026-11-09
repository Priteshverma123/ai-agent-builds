"""Typed settings loaded from the environment: the single source of truth for configuration.

Read at call time (not import time) so tests and CI jobs can change behaviour with env vars.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path(raw: str | None, default: Path) -> Path:
    return Path(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                                         # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None                                       # LLM_MODEL: provider model id
    suite: Path = PROJECT_ROOT / "examples" / "support_suite.json"     # EVAL_SUITE: suite JSON to run
    baseline: Path = PROJECT_ROOT / "examples" / "baseline.json"       # EVAL_BASELINE: results to compare with
    out_dir: Path = PROJECT_ROOT / "out"                               # EVAL_OUT_DIR: JSON + Markdown reports
    trials: int = 1                                                    # EVAL_TRIALS: repeats per case
    max_steps: int = 4                                                 # AGENT_MAX_STEPS: agent turns per case

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        default = cls()
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            suite=_path(env.get("EVAL_SUITE"), default.suite),
            baseline=_path(env.get("EVAL_BASELINE"), default.baseline),
            out_dir=_path(env.get("EVAL_OUT_DIR"), default.out_dir),
            trials=int(env.get("EVAL_TRIALS") or 1),
            max_steps=int(env.get("AGENT_MAX_STEPS") or 4),
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
