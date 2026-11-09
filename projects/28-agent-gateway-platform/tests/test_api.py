"""End-to-end through HTTP: status codes, headers, metering and audit."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from conftest import ACME, HOBBY, OPS, auth, req
from gateway.domain.errors import GatewayError

CHAT = {"messages": [{"role": "user", "content": "What is a token bucket?"}]}


def test_health(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_missing_and_bad_keys_are_401(client) -> None:
    assert client.post("/v1/chat", json=CHAT).status_code == 401
    r = client.post("/v1/chat", json=CHAT, headers=auth("sk-nope"))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"


def test_x_api_key_header_also_works(client) -> None:
    assert client.post("/v1/chat", json=CHAT, headers={"X-API-Key": ACME}).status_code == 200


def test_invalid_body_is_422(client) -> None:
    assert client.post("/v1/chat", json={"messages": []}, headers=auth(ACME)).status_code == 422


def test_chat_then_cache_hit_is_free(client) -> None:
    first = client.post("/v1/chat", json=CHAT, headers=auth(ACME))
    second = client.post("/v1/chat", json=CHAT, headers=auth(ACME))
    assert first.headers["X-Cache"] == "MISS" and second.headers["X-Cache"] == "HIT"
    assert first.json()["content"] == second.json()["content"]
    assert second.json()["usage"]["cost_usd"] == 0.0
    usage = client.get("/v1/usage", headers=auth(ACME)).json()
    assert usage["requests"] == 2 and usage["cached_hits"] == 1


def test_cache_does_not_leak_across_tenants(client, clock) -> None:
    client.post("/v1/chat", json=CHAT, headers=auth(ACME))
    r = client.post("/v1/chat", json=CHAT, headers=auth(HOBBY))
    assert r.headers["X-Cache"] == "MISS"


def test_rate_limit_429_with_retry_after(client) -> None:
    body = {**CHAT, "temperature": 0.5}
    codes = [client.post("/v1/chat", json=body, headers=auth(HOBBY)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.post("/v1/chat", json=body, headers=auth(HOBBY))
    assert r.headers["Retry-After"] == "10"


def test_budget_hard_stop_is_402(client, clock) -> None:
    body = {"messages": [{"role": "user", "content": "write an essay"}], "max_tokens": 250, "temperature": 0.3}
    codes = []
    for _ in range(4):
        clock.advance(60)
        codes.append(client.post("/v1/chat", json=body, headers=auth(HOBBY)).status_code)
    assert codes == [200, 200, 402, 402]
    usage = client.get("/v1/usage", headers=auth(HOBBY)).json()
    assert usage["cost_usd"] <= usage["budget_usd"]


def test_fallback_and_503(client, container) -> None:
    container.providers["alpha"].set_down(True)
    r = client.post("/v1/chat", json=CHAT, headers=auth(ACME))
    assert r.json()["model"] == "beta-fast" and r.json()["fallback_from"] == ["alpha-fast"]
    container.providers["beta"].set_down(True)
    r = client.post("/v1/chat", json={**CHAT, "temperature": 0.2}, headers=auth(ACME))
    assert r.status_code == 503 and r.json()["error"]["code"] == "all_providers_failed"
    assert client.get("/v1/usage", headers=auth(ACME)).json()["budget_remaining_usd"] > 4.99


def test_usage_isolation_and_admin(client) -> None:
    assert client.get("/v1/usage?tenant=acme", headers=auth(HOBBY)).status_code == 403
    assert client.get("/v1/usage?tenant=acme", headers=auth(OPS)).json()["tenant"] == "acme"


def test_audit_requires_admin_and_hides_prompts(client) -> None:
    secret = "my password is hunter2"
    client.post("/v1/chat", json={"messages": [{"role": "user", "content": secret}]}, headers=auth(ACME))
    assert client.get("/v1/audit", headers=auth(ACME)).status_code == 403
    audit = client.get("/v1/audit", headers=auth(OPS)).json()
    assert audit["verified"] is True and len(audit["entries"]) == 1
    assert "hunter2" not in str(audit)


def test_load_metering_is_consistent(container) -> None:
    """Every request is accounted for exactly once, even under contention."""
    service = container.service
    ops_req = req("ping", temperature=0.9)

    def one(_: int) -> int:
        try:
            service.chat(OPS, ops_req)
            return 200
        except GatewayError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=32) as pool:
        codes = list(pool.map(one, range(300)))
    snap = service.meter.snapshot("ops")
    assert codes.count(200) == 50  # internal plan burst
    assert snap["requests"] == 50 and snap["rejected"]["rate_limited"] == 250
    assert len(service.audit.entries("ops")) == 300 and service.audit.verify()[0]
