"""Typed settings loaded from environment variables: the single source of truth.

Every knob the project reads lives here, with a safe default, so ``.env.example``,
the CLI and the Dockerfile all describe the same thing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"  # mock | anthropic | openai
    llm_model: str | None = None  # None = the provider's default model
    servers_config: Path = EXAMPLES / "servers.json"  # which MCP servers to launch
    tasks_file: Path = EXAMPLES / "tasks.txt"  # one task per line for the demo
    mcp_timeout: float = 10.0  # seconds to wait for any single MCP reply
    max_steps: int = 6  # agent loop budget per task

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            llm_provider=env.get("LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("LLM_MODEL") or None,
            servers_config=Path(env.get("MCP_SERVERS_CONFIG", str(EXAMPLES / "servers.json"))),
            tasks_file=Path(env.get("AGENT_TASKS_FILE", str(EXAMPLES / "tasks.txt"))),
            mcp_timeout=float(env.get("MCP_TIMEOUT", "10")),
            max_steps=int(env.get("AGENT_MAX_STEPS", "6")),
        )
