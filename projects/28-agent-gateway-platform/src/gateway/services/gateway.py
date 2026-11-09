"""The request pipeline. Read `chat()` top to bottom: that IS the architecture.

    authenticate -> rate limit -> route -> cache? -> reserve budget -> call (with fallback)
                 -> commit cost -> cache put -> meter -> audit
"""
from __future__ import annotations

import itertools
from typing import Any, Callable

from gateway.adapters.keystore import KeyStore
from gateway.adapters.providers import estimate_tokens
from gateway.domain.errors import AllProvidersFailed, Forbidden, GatewayError
from gateway.domain.models import ChatRequest, ChatResponse, Tenant, Usage
from gateway.services.audit import AuditLog, fingerprint
from gateway.services.budget import BudgetLedger
from gateway.services.cache import ResponseCache, cache_key, is_cacheable
from gateway.services.metering import UsageMeter
from gateway.services.ratelimit import RateLimiter
from gateway.services.router import ModelRouter

EventHook = Callable[[str, dict[str, Any]], None]


class GatewayService:
    def __init__(self, keys: KeyStore, limiter: RateLimiter, budget: BudgetLedger, cache: ResponseCache,
                 router: ModelRouter, meter: UsageMeter, audit: AuditLog, on_event: EventHook | None = None) -> None:
        self.keys, self.limiter, self.budget, self.cache = keys, limiter, budget, cache
        self.router, self.meter, self.audit = router, meter, audit
        self._emit = on_event or (lambda stage, data: None)
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ public API
    def chat(self, api_key: str | None, request: ChatRequest) -> ChatResponse:
        request_id = f"req_{next(self._ids):04d}"
        tenant = self.keys.authenticate(api_key)  # 401 before we spend anything
        self._emit("auth", {"tenant": tenant.id, "plan": tenant.plan.name})
        try:
            return self._handle(request_id, tenant, request)
        except GatewayError as exc:
            self.meter.record_rejection(tenant.id, exc.code)
            self.audit.append("chat.rejected", request_id=request_id, tenant=tenant.id, code=exc.code,
                              prompt_fp=fingerprint(request.prompt_text()))
            self._emit("rejected", {"code": exc.code, "status": exc.status, "message": exc.message})
            raise

    def usage(self, caller: Tenant, tenant_id: str | None = None) -> dict[str, Any]:
        target = tenant_id or caller.id
        if target != caller.id and not caller.is_admin:
            raise Forbidden("only admin keys can read other tenants' usage")
        tenant = self.keys.tenant(target)
        if tenant is None:
            raise Forbidden(f"unknown tenant '{target}'")
        return {"tenant": target, "plan": tenant.plan.name,
                "budget_usd": tenant.plan.monthly_budget_usd,
                "budget_remaining_usd": round(self.budget.remaining(tenant), 8),
                **self.meter.snapshot(target)}

    # ------------------------------------------------------------------ pipeline
    def _handle(self, request_id: str, tenant: Tenant, request: ChatRequest) -> ChatResponse:
        left = self.limiter.acquire(tenant)
        self._emit("ratelimit", {"tokens_left": round(left, 2), "burst": tenant.plan.burst})

        route = self.router.route(request, tenant)
        self._emit("route", {"requested": request.model, "chain": [m.name for m in route]})

        key = cache_key(tenant.id, route[0].name, request) if is_cacheable(request) else None
        if key and (hit := self.cache.get(key)):
            self._emit("cache", {"result": "HIT"})
            return self._finish_cached(request_id, tenant, hit)
        self._emit("cache", {"result": "MISS" if key else "SKIP (temperature > 0)"})

        input_tokens = estimate_tokens(request.prompt_text())
        reservation = self.budget.reserve(
            tenant, self.router.worst_case_cost(route, input_tokens, request.max_tokens))
        self._emit("budget", {"reserved": reservation.amount, "remaining": self.budget.remaining(tenant)})

        try:
            routed = self.router.call_with_fallback(route, request)
        except AllProvidersFailed:
            self.budget.release(reservation)
            raise
        for attempt in routed.attempts:
            self._emit("provider", {"model": attempt.model, "provider": attempt.provider, "outcome": attempt.outcome})

        c, spec = routed.completion, routed.spec
        cost = spec.cost(c.input_tokens, c.output_tokens)
        self.budget.commit(reservation, cost)
        response = ChatResponse(
            id=request_id, tenant=tenant.id, model=spec.name, provider=spec.provider, content=c.text,
            usage=Usage(input_tokens=c.input_tokens, output_tokens=c.output_tokens, cost_usd=cost),
            fallback_from=[a.model for a in routed.attempts if a.outcome != "ok"])
        if key:
            self.cache.put(key, response)
        self.meter.record_success(tenant.id, spec.name, c.input_tokens, c.output_tokens, cost, cached=False)
        self.audit.append("chat.ok", request_id=request_id, tenant=tenant.id, model=spec.name,
                          cost_usd=cost, fallback=bool(response.fallback_from),
                          prompt_fp=fingerprint(request.prompt_text()))
        self._emit("commit", {"cost": cost, "remaining": self.budget.remaining(tenant)})
        return response

    def _finish_cached(self, request_id: str, tenant: Tenant, hit: ChatResponse) -> ChatResponse:
        response = hit.model_copy(update={
            "id": request_id, "cached": True, "fallback_from": [],
            "usage": Usage(input_tokens=0, output_tokens=0, cost_usd=0.0)})
        self.meter.record_success(tenant.id, hit.model, 0, 0, 0.0, cached=True)
        self.audit.append("chat.cached", request_id=request_id, tenant=tenant.id, model=hit.model, cost_usd=0.0)
        self._emit("commit", {"cost": 0.0, "remaining": self.budget.remaining(tenant)})
        return response
