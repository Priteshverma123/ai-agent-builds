"""Composition root: the only place that knows which concrete adapters are plugged in."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gateway.adapters.clock import Clock, SystemClock
from gateway.adapters.keystore import KeyStore
from gateway.adapters.providers import MockLLM, Provider
from gateway.config import Settings
from gateway.services.audit import AuditLog
from gateway.services.budget import BudgetLedger
from gateway.services.cache import ResponseCache
from gateway.services.gateway import EventHook, GatewayService
from gateway.services.metering import UsageMeter
from gateway.services.ratelimit import RateLimiter
from gateway.services.router import CircuitBreaker, ModelRouter

DEFAULT_TENANTS = Settings().tenants_path


@dataclass
class Container:
    service: GatewayService
    providers: dict[str, Provider]
    clock: Clock


def default_providers(settings: Settings | None = None) -> dict[str, Provider]:
    """MockLLM unless LLM_PROVIDER is set. Two named providers so fallback has somewhere to go."""
    settings = settings or Settings.from_env()
    if settings.llm_provider in ("anthropic", "openai"):
        from gateway.adapters.real_llm import HttpProvider
        return {name: HttpProvider(name, settings.llm_provider, settings) for name in ("alpha", "beta")}
    return {"alpha": MockLLM("alpha"), "beta": MockLLM("beta")}


def build(tenants_path: Path | None = None, clock: Clock | None = None,
          providers: dict[str, Provider] | None = None, on_event: EventHook | None = None,
          audit_path: Path | None = None, settings: Settings | None = None) -> Container:
    """Wire the gateway. Explicit arguments win over `Settings` (which defaults to the environment)."""
    settings = settings or Settings.from_env()
    clock = clock or SystemClock()
    providers = providers or default_providers(settings)
    service = GatewayService(
        keys=KeyStore.from_file(tenants_path or settings.tenants_path),
        limiter=RateLimiter(clock),
        budget=BudgetLedger(),
        cache=ResponseCache(clock, max_entries=settings.cache_max_entries, ttl_s=settings.cache_ttl_s),
        router=ModelRouter(providers, CircuitBreaker(clock, threshold=settings.breaker_threshold,
                                                     cooldown_s=settings.breaker_cooldown_s)),
        meter=UsageMeter(),
        audit=AuditLog(audit_path or settings.audit_path),
        on_event=on_event,
    )
    return Container(service=service, providers=providers, clock=clock)
