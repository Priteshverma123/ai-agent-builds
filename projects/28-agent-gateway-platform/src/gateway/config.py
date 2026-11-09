"""Typed settings loaded from the environment: the single source of truth for every knob.

`container.build()` and `serve.py` read these; nothing else touches `os.environ`. Defaults run fully
offline with the MockLLM and match the numbers the demo and tests expect.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_model_map(raw: str) -> dict[str, str]:
    """``"alpha-fast=claude-haiku-4-5,alpha-pro=..."`` -> ``{"alpha-fast": "claude-haiku-4-5", ...}``."""
    pairs = [p.split("=", 1) for p in raw.split(",") if "=" in p]
    return {k.strip(): v.strip() for k, v in pairs}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                                   # mock | anthropic | openai
    model_map: dict[str, str] = field(default_factory=dict)      # gateway model name -> real model id
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    provider_timeout_s: float = 30.0
    tenants_path: Path = PROJECT_ROOT / "examples" / "tenants.json"
    audit_path: Path | None = None                               # None = in-memory audit log
    cache_ttl_s: float = 300.0
    cache_max_entries: int = 1_000
    breaker_threshold: int = 3                                   # consecutive failures that open a circuit
    breaker_cooldown_s: float = 30.0
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()
        return cls(
            llm_provider=(env.get("LLM_PROVIDER") or d.llm_provider).strip().lower(),
            model_map=parse_model_map(env.get("MODEL_MAP", "")),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            openai_api_key=env.get("OPENAI_API_KEY", ""),
            provider_timeout_s=float(env.get("PROVIDER_TIMEOUT_S") or d.provider_timeout_s),
            tenants_path=Path(env["GATEWAY_TENANTS"]) if env.get("GATEWAY_TENANTS") else d.tenants_path,
            audit_path=Path(env["GATEWAY_AUDIT_FILE"]) if env.get("GATEWAY_AUDIT_FILE") else None,
            cache_ttl_s=float(env.get("CACHE_TTL_S") or d.cache_ttl_s),
            cache_max_entries=int(env.get("CACHE_MAX_ENTRIES") or d.cache_max_entries),
            breaker_threshold=int(env.get("BREAKER_THRESHOLD") or d.breaker_threshold),
            breaker_cooldown_s=float(env.get("BREAKER_COOLDOWN_S") or d.breaker_cooldown_s),
            host=env.get("HOST") or d.host,
            port=int(env.get("PORT") or d.port),
        )
