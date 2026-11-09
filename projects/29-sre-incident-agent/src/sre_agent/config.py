"""Typed settings loaded from the environment: the single source of truth for every knob.

`cli.py` reads these once and hands them to the demo, the LLM factory and the agent. Defaults run
fully offline with the MockLLM policy and the sample incident in `examples/`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-5", "openai": "gpt-4o-mini"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                     # mock | anthropic | openai
    llm_model: str = ""                            # empty -> DEFAULT_MODELS[provider]
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    examples_dir: Path = PROJECT_ROOT / "examples"  # alert.json, runbooks.json, incident/
    out_dir: Path = PROJECT_ROOT / "out"            # postmortem.md lands here
    max_steps: int = 15                            # think -> act -> observe iterations before giving up

    @property
    def model(self) -> str:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, "")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()
        return cls(
            llm_provider=(env.get("LLM_PROVIDER") or d.llm_provider).strip().lower(),
            llm_model=env.get("LLM_MODEL", d.llm_model),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            openai_api_key=env.get("OPENAI_API_KEY", ""),
            examples_dir=Path(env["SRE_EXAMPLES_DIR"]) if env.get("SRE_EXAMPLES_DIR") else d.examples_dir,
            out_dir=Path(env["SRE_OUT_DIR"]) if env.get("SRE_OUT_DIR") else d.out_dir,
            max_steps=int(env.get("SRE_MAX_STEPS") or d.max_steps),
        )
