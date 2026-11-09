"""Cache, routing/fallback/circuit breaker and the audit chain."""
from __future__ import annotations

import pytest

from conftest import make_tenant, req
from gateway.adapters.clock import FakeClock
from gateway.adapters.providers import MockLLM
from gateway.domain.errors import AllProvidersFailed, Forbidden
from gateway.domain.models import ChatResponse, Usage
from gateway.services.audit import AuditLog
from gateway.services.cache import ResponseCache, cache_key, is_cacheable
from gateway.services.router import CircuitBreaker, ModelRouter


def _resp(text: str) -> ChatResponse:
    return ChatResponse(id="r", tenant="t", model="m", provider="p", content=text,
                        usage=Usage(input_tokens=1, output_tokens=1, cost_usd=0.1))


def _router(clock: FakeClock) -> tuple[ModelRouter, MockLLM, MockLLM]:
    alpha, beta = MockLLM("alpha"), MockLLM("beta")
    return ModelRouter({"alpha": alpha, "beta": beta}, CircuitBreaker(clock, threshold=2, cooldown_s=30)), alpha, beta


# ------------------------------------------------------------------ cache
def test_cache_key_is_isolated_per_tenant() -> None:
    r = req()
    assert cache_key("acme", "alpha-fast", r) != cache_key("globex", "alpha-fast", r)
    assert cache_key("acme", "alpha-fast", r) == cache_key("acme", "alpha-fast", req())


def test_only_deterministic_requests_are_cacheable() -> None:
    assert is_cacheable(req(temperature=0.0))
    assert not is_cacheable(req(temperature=0.7))


def test_cache_ttl_and_lru_eviction() -> None:
    clock = FakeClock()
    cache = ResponseCache(clock, max_entries=2, ttl_s=10)
    cache.put("a", _resp("A"))
    cache.put("b", _resp("B"))
    assert cache.get("a").content == "A"  # touch a -> b is now least recently used
    cache.put("c", _resp("C"))
    assert cache.get("b") is None
    clock.advance(11)
    assert cache.get("a") is None and cache.get("c") is None


# ------------------------------------------------------------------ router
def test_auto_routes_by_difficulty() -> None:
    router, _, _ = _router(FakeClock())
    tenant = make_tenant()
    assert [m.name for m in router.route(req("hi there"), tenant)] == ["alpha-fast", "beta-fast"]
    assert router.route(req("Please analyze this outage"), tenant)[0].name == "alpha-pro"
    assert router.route(req("word " * 300), tenant)[0].tier == "pro"


def test_route_respects_plan() -> None:
    router, _, _ = _router(FakeClock())
    free = make_tenant(models=("alpha-fast", "beta-fast"))
    assert [m.name for m in router.route(req("Analyze it"), free)] == ["alpha-fast", "beta-fast"]
    with pytest.raises(Forbidden):
        router.route(req(model="alpha-pro"), free)
    with pytest.raises(Forbidden):
        router.route(req(model="gpt-unknown"), free)


def test_fallback_on_provider_error() -> None:
    router, alpha, _ = _router(FakeClock())
    alpha.fail_next(1)
    routed = router.call_with_fallback(router.route(req(), make_tenant()), req())
    assert routed.spec.name == "beta-fast"
    assert [a.outcome.split(":")[0] for a in routed.attempts] == ["error", "ok"]


def test_circuit_opens_then_half_opens_after_cooldown() -> None:
    clock = FakeClock()
    router, alpha, _ = _router(clock)
    route = router.route(req(), make_tenant())
    alpha.set_down(True)
    router.call_with_fallback(route, req())
    router.call_with_fallback(route, req())  # 2nd failure -> open
    calls = alpha.calls
    routed = router.call_with_fallback(route, req())
    assert routed.attempts[0].outcome == "skipped: circuit open" and alpha.calls == calls
    alpha.set_down(False)
    clock.advance(31)
    assert router.call_with_fallback(route, req()).spec.name == "alpha-fast"


def test_all_providers_down_raises_503() -> None:
    router, alpha, beta = _router(FakeClock())
    alpha.set_down(True)
    beta.set_down(True)
    with pytest.raises(AllProvidersFailed) as err:
        router.call_with_fallback(router.route(req(), make_tenant()), req())
    assert err.value.status == 503


def test_mock_respects_max_tokens() -> None:
    out = MockLLM("alpha").complete("alpha-fast", req("write an essay").messages, max_tokens=40, temperature=0)
    assert 30 <= out.output_tokens <= 40


# ------------------------------------------------------------------ audit
def test_audit_chain_detects_tampering() -> None:
    log = AuditLog()
    for i in range(5):
        log.append("chat.ok", tenant="acme", cost_usd=0.01 * i)
    assert log.verify() == (True, None)
    log._entries[2]["cost_usd"] = 0.0
    assert log.verify() == (False, 3)


def test_audit_deletion_is_detected() -> None:
    log = AuditLog()
    for _ in range(3):
        log.append("chat.ok", tenant="acme")
    del log._entries[1]
    assert log.verify()[0] is False


def test_audit_writes_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append("chat.ok", tenant="acme")
    log.append("chat.rejected", tenant="acme")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
