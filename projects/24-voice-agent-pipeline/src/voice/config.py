"""Typed settings loaded from the environment: the single source of truth for configuration.

Nothing else in the package calls ``os.getenv``; it asks :func:`load_settings` instead. Defaults are
exactly what the offline demo uses.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"                      # mock | anthropic | openai
    llm_model: str | None = None                    # None -> the provider's default model
    mode: Literal["streaming", "batch"] = "streaming"
    filler_after_ms: float | None = 450             # None disables the "One moment." filler
    budget_total_ms: float = 1000                   # voice-to-voice target per turn
    script_path: Path = PROJECT_ROOT / "examples" / "conversation.json"  # the mock caller

    @property
    def use_mock(self) -> bool:
        return self.llm_provider in ("", "mock")


def _optional_ms(raw: str | None, default: float | None) -> float | None:
    if raw is None:
        return default
    return None if raw.strip().lower() in ("", "off", "none") else float(raw)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build :class:`Settings` from ``env`` (defaults to ``os.environ``); unset keys keep defaults."""
    env = os.environ if env is None else env
    d = Settings()
    mode = env.get("VOICE_MODE", d.mode).strip().lower()
    if mode not in ("streaming", "batch"):
        raise ValueError(f"VOICE_MODE must be 'streaming' or 'batch', got {mode!r}")
    return Settings(
        llm_provider=env.get("LLM_PROVIDER", d.llm_provider).strip().lower(),
        llm_model=env.get("LLM_MODEL") or None,
        mode=mode,
        filler_after_ms=_optional_ms(env.get("FILLER_AFTER_MS"), d.filler_after_ms),
        budget_total_ms=float(env.get("LATENCY_BUDGET_MS", d.budget_total_ms)),
        script_path=Path(env.get("CONVERSATION_SCRIPT") or d.script_path),
    )
