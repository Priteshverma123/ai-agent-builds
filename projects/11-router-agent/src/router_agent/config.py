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
    threshold: float = 0.6  # minimum classifier confidence to dispatch to a specialist
    intents_file: Path = EXAMPLES / "intents.json"  # intent descriptions + few-shot examples
    labelled_file: Path = EXAMPLES / "labelled.jsonl"  # eval set: one {"message", "intent"} per line

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            llm_provider=env.get("LLM_PROVIDER", "mock").lower(),
            llm_model=env.get("LLM_MODEL") or None,
            threshold=float(env.get("ROUTER_THRESHOLD", "0.6")),
            intents_file=Path(env.get("ROUTER_INTENTS_FILE", str(EXAMPLES / "intents.json"))),
            labelled_file=Path(env.get("ROUTER_LABELLED_FILE", str(EXAMPLES / "labelled.jsonl"))),
        )
