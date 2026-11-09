"""Typed settings loaded from the environment: the single source of truth for configuration.

Read at call time (not import time) so tests and containers can change behaviour with env vars.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def _domains(raw: str | None) -> tuple[str, ...]:
    parts = tuple(d.strip().lower() for d in (raw or "").split(",") if d.strip())
    return parts or ("acme.example",)


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                 # LLM_PROVIDER: mock | anthropic | openai
    llm_model: str | None = None               # LLM_MODEL: provider model id (provider default if unset)
    state_dir: Path = Path(".hitl_state")      # HITL_STATE_DIR: runs, back office and audit log live here
    max_steps: int = 10                        # AGENT_MAX_STEPS: model turns before a run fails
    company_domains: tuple[str, ...] = ("acme.example",)  # RISK_COMPANY_DOMAINS: comma list, internal mail
    large_amount: float = 100.0                # RISK_LARGE_AMOUNT: refunds above this score +20
    very_large_amount: float = 1000.0          # RISK_VERY_LARGE_AMOUNT: refunds above this score +35

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        return cls(
            llm_provider=(env.get("LLM_PROVIDER", "mock").strip().lower() or "mock"),
            llm_model=env.get("LLM_MODEL") or None,
            state_dir=Path(env.get("HITL_STATE_DIR") or ".hitl_state"),
            max_steps=int(env.get("AGENT_MAX_STEPS") or 10),
            company_domains=_domains(env.get("RISK_COMPANY_DOMAINS")),
            large_amount=float(env.get("RISK_LARGE_AMOUNT") or 100.0),
            very_large_amount=float(env.get("RISK_VERY_LARGE_AMOUNT") or 1000.0),
        )


def load_settings() -> Settings:
    """Read settings from the current process environment."""
    return Settings.from_env()
