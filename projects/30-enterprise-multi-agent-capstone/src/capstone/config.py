"""Typed settings loaded from the environment: the single source of truth for every knob.

`container.build()`, `serve.py`, `cli.py` and the MCP stdio server read these; nothing else touches
`os.environ`. Defaults run fully offline with the MockLLM and the sample handbook in `examples/docs`.
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
    llm_provider: str = "mock"                                  # mock | anthropic | openai
    llm_model: str = ""                                         # empty -> DEFAULT_MODELS[provider]
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    docs_dir: Path = PROJECT_ROOT / "examples" / "docs"         # the handbook RAG indexes
    evals_path: Path = PROJECT_ROOT / "examples" / "evals.json"
    trace_file: Path = Path("out/traces.jsonl")                 # where the HTTP server appends traces
    max_steps: int = 6                                          # plan steps the orchestrator will run
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def model(self) -> str:
        return self.llm_model or DEFAULT_MODELS.get(self.llm_provider, "")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()

        def path(name: str, default: Path) -> Path:
            return Path(env[name]) if env.get(name) else default

        return cls(
            llm_provider=(env.get("LLM_PROVIDER") or d.llm_provider).strip().lower(),
            llm_model=env.get("LLM_MODEL", d.llm_model),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            openai_api_key=env.get("OPENAI_API_KEY", ""),
            docs_dir=path("DOCS_DIR", d.docs_dir),
            evals_path=path("EVALS_FILE", d.evals_path),
            trace_file=path("TRACE_FILE", d.trace_file),
            max_steps=int(env.get("ORCHESTRATOR_MAX_STEPS") or d.max_steps),
            host=env.get("HOST") or d.host,
            port=int(env.get("PORT") or d.port),
        )
