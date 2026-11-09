"""Model routing + fallback + circuit breaker.

route():           request -> ordered list of models to try (filtered by the tenant's plan)
call_with_fallback(): try each model; on ProviderError move to the next one
CircuitBreaker:    after N consecutive failures a provider is skipped for `cooldown_s` seconds,
                   so an outage costs one failed call, not one per request.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from gateway.adapters.clock import Clock
from gateway.adapters.providers import Provider, estimate_tokens
from gateway.domain.errors import AllProvidersFailed, Forbidden, ProviderError
from gateway.domain.models import ChatRequest, Completion, ModelSpec, Tenant

HARD_TASK = re.compile(r"\b(analy[sz]e|plan|design|compare|debug|reason|architecture)\b", re.I)

DEFAULT_CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec("alpha-fast", "alpha", "fast", input_per_1k=0.0005, output_per_1k=0.0015),
    ModelSpec("alpha-pro", "alpha", "pro", input_per_1k=0.0030, output_per_1k=0.0150),
    ModelSpec("beta-fast", "beta", "fast", input_per_1k=0.0006, output_per_1k=0.0018),
    ModelSpec("beta-pro", "beta", "pro", input_per_1k=0.0035, output_per_1k=0.0160),
)

# Preferred order per tier: same tier on another provider first, then degrade a tier.
FALLBACK_CHAINS = {
    "fast": ["alpha-fast", "beta-fast"],
    "pro": ["alpha-pro", "beta-pro", "alpha-fast", "beta-fast"],
}


@dataclass
class CircuitBreaker:
    clock: Clock
    threshold: int = 3
    cooldown_s: float = 30.0
    _failures: dict[str, int] = field(default_factory=dict)
    _opened_at: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_open(self, provider: str) -> bool:
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened is None:
                return False
            if self.clock.now() - opened >= self.cooldown_s:  # half-open: allow a probe
                del self._opened_at[provider]
                self._failures[provider] = self.threshold - 1
                return False
            return True

    def record(self, provider: str, ok: bool) -> None:
        with self._lock:
            if ok:
                self._failures[provider] = 0
                return
            self._failures[provider] = self._failures.get(provider, 0) + 1
            if self._failures[provider] >= self.threshold:
                self._opened_at[provider] = self.clock.now()


@dataclass(frozen=True)
class Attempt:
    model: str
    provider: str
    outcome: str  # "ok" | "error: ..." | "skipped: circuit open"


@dataclass(frozen=True)
class RoutedCompletion:
    completion: Completion
    spec: ModelSpec
    attempts: list[Attempt]


class ModelRouter:
    def __init__(self, providers: dict[str, Provider], breaker: CircuitBreaker,
                 catalog: tuple[ModelSpec, ...] = DEFAULT_CATALOG) -> None:
        self.providers = providers
        self.breaker = breaker
        self.catalog = {m.name: m for m in catalog}

    def pick_tier(self, request: ChatRequest) -> str:
        """The 'auto' policy: long or reasoning-heavy prompts go to the pro tier."""
        text = request.prompt_text()
        return "pro" if estimate_tokens(text) > 200 or HARD_TASK.search(text) else "fast"

    def route(self, request: ChatRequest, tenant: Tenant) -> list[ModelSpec]:
        if request.model == "auto":
            chain = FALLBACK_CHAINS[self.pick_tier(request)]
        elif request.model in self.catalog:
            if request.model not in tenant.plan.allowed_models:
                raise Forbidden(f"plan '{tenant.plan.name}' does not include model '{request.model}'")
            tier = self.catalog[request.model].tier
            chain = [request.model] + [m for m in FALLBACK_CHAINS[tier] if m != request.model]
        else:
            raise Forbidden(f"unknown model '{request.model}'")
        allowed = [self.catalog[m] for m in chain if m in tenant.plan.allowed_models]
        if not allowed:
            raise Forbidden(f"plan '{tenant.plan.name}' does not include model '{request.model}'")
        return allowed

    @staticmethod
    def worst_case_cost(route: list[ModelSpec], input_tokens: int, max_tokens: int) -> float:
        """Upper bound used for the budget reservation: the priciest model, full max_tokens."""
        return max(spec.cost(input_tokens, max_tokens) for spec in route)

    def call_with_fallback(self, route: list[ModelSpec], request: ChatRequest) -> RoutedCompletion:
        attempts: list[Attempt] = []
        for spec in route:
            if self.breaker.is_open(spec.provider):
                attempts.append(Attempt(spec.name, spec.provider, "skipped: circuit open"))
                continue
            try:
                completion = self.providers[spec.provider].complete(
                    spec.name, request.messages, request.max_tokens, request.temperature)
            except ProviderError as exc:
                self.breaker.record(spec.provider, ok=False)
                attempts.append(Attempt(spec.name, spec.provider, f"error: {exc}"))
                continue
            self.breaker.record(spec.provider, ok=True)
            attempts.append(Attempt(spec.name, spec.provider, "ok"))
            return RoutedCompletion(completion, spec, attempts)
        raise AllProvidersFailed("every model in the route failed: " +
                                 "; ".join(f"{a.model} -> {a.outcome}" for a in attempts))
