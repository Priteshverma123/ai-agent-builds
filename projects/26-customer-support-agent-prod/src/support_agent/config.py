"""All configuration comes from environment variables (12-factor style)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_date(name: str) -> date | None:
    raw = os.getenv(name)
    return date.fromisoformat(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    data_dir: Path = PROJECT_ROOT / "examples"
    llm_provider: str = "mock"          # mock | anthropic | openai
    llm_model: str = ""                 # provider default when empty
    refund_window_days: int = 30
    refund_auto_approve_limit: float = 200.0
    max_agent_steps: int = 6
    api_key: str | None = None          # if set, clients must send X-API-Key
    log_level: str = "INFO"
    today: date | None = None           # pinned clock for demos/tests; None = real date
    trace_capacity: int = 500

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.getenv("SUPPORT_DATA_DIR", str(PROJECT_ROOT / "examples"))),
            llm_provider=os.getenv("LLM_PROVIDER", "mock").lower(),
            llm_model=os.getenv("LLM_MODEL", ""),
            refund_window_days=int(os.getenv("REFUND_WINDOW_DAYS", "30")),
            refund_auto_approve_limit=float(os.getenv("REFUND_AUTO_APPROVE_LIMIT", "200")),
            max_agent_steps=int(os.getenv("MAX_AGENT_STEPS", "6")),
            api_key=os.getenv("SUPPORT_API_KEY") or None,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            today=_env_date("SUPPORT_TODAY"),
            trace_capacity=int(os.getenv("TRACE_CAPACITY", "500")),
        )

    def current_date(self) -> date:
        return self.today or date.today()
