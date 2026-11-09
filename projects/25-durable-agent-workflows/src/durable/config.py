"""Typed settings loaded from the environment: the single source of truth for every knob.

Read once per process with :meth:`Settings.from_env`. Defaults keep the project offline and
deterministic; ``.env.example`` lists every variable read here.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"   # mock | anthropic | openai
    llm_model: str | None = None  # None -> the provider's default model
    data_dir: Path = Path(tempfile.gettempdir()) / "durable_agent_demo"  # journal.db + world.db for the demo
    lease_s: float = 1.0          # how long a worker's claim on a run lasts without a heartbeat

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        defaults = cls()
        return cls(
            llm_provider=env.get("LLM_PROVIDER", defaults.llm_provider).strip().lower() or "mock",
            llm_model=env.get("LLM_MODEL") or None,
            data_dir=Path(env["DURABLE_DATA_DIR"]) if env.get("DURABLE_DATA_DIR") else defaults.data_dir,
            lease_s=float(env.get("DURABLE_LEASE_S") or defaults.lease_s),
        )
