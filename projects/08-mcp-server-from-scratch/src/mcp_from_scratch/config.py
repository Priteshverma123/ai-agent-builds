"""Typed settings loaded from environment variables: the single source of truth.

The server has no secrets and no network: the only knobs are where its seed data lives.
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
    notes_file: Path = EXAMPLES / "notes.json"  # seed notes loaded at server start (kept in memory)
    handbook_file: Path = EXAMPLES / "handbook.md"  # served as the docs://handbook resource

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            notes_file=Path(env.get("MCP_NOTES_FILE", str(EXAMPLES / "notes.json"))),
            handbook_file=Path(env.get("MCP_HANDBOOK_FILE", str(EXAMPLES / "handbook.md"))),
        )
