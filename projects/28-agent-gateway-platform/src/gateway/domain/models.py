"""Domain objects: tenants, plans, models and the public request/response contract.

Nothing in this module does I/O. Services and adapters depend on it; it depends on nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- tenants & plans
@dataclass(frozen=True)
class Plan:
    """What a customer pays for: throughput, spend ceiling and which models they may use."""

    name: str
    requests_per_minute: int
    burst: int
    monthly_budget_usd: float
    allowed_models: tuple[str, ...]


@dataclass(frozen=True)
class Tenant:
    """One customer of the gateway. API keys map to exactly one tenant."""

    id: str
    name: str
    plan: Plan
    is_admin: bool = False


# ---------------------------------------------------------------- model catalog
@dataclass(frozen=True)
class ModelSpec:
    """A model the gateway can call, which provider serves it, and what it costs per 1k tokens."""

    name: str
    provider: str
    tier: Literal["fast", "pro"]
    input_per_1k: float
    output_per_1k: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return round(input_tokens / 1000 * self.input_per_1k + output_tokens / 1000 * self.output_per_1k, 8)


@dataclass(frozen=True)
class Completion:
    """What a provider adapter returns."""

    text: str
    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------- HTTP contract
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    """Body of POST /v1/chat. `model="auto"` lets the router pick a tier."""

    model: str = "auto"
    messages: list[Message] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=128, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    def prompt_text(self) -> str:
        return "\n".join(f"{m.role}: {m.content}" for m in self.messages)


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ChatResponse(BaseModel):
    id: str
    tenant: str
    model: str
    provider: str
    content: str
    usage: Usage
    cached: bool = False
    fallback_from: list[str] = Field(default_factory=list)
