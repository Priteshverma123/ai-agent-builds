"""Demo: real HTTP calls (in-process) through the gateway, with a teaching trace of every stage.

Run:  python demo.py   (or `gateway demo` once installed)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from gateway.adapters.clock import FakeClock
from gateway.api.app import create_app
from gateway.container import build
from gateway.domain.errors import GatewayError
from gateway.domain.models import ChatRequest

KEYS = {"acme": "sk-acme-demo-0001", "hobby": "sk-hobby-demo-0002", "ops": "sk-ops-admin-0003"}
WIDTH = 74


def banner(title: str) -> None:
    print("\n+" + "-" * (WIDTH - 2) + "+")
    print("| " + title.ljust(WIDTH - 4) + " |")
    print("+" + "-" * (WIDTH - 2) + "+")


class Trace:
    """Receives pipeline events from the service and prints them as aligned rows."""

    def __init__(self) -> None:
        self.verbose = True
        self.attempts: list[str] = []

    def __call__(self, stage: str, data: dict) -> None:
        if not self.verbose:
            if stage == "provider":
                mark = {"ok": "ok", "skipped: circuit open": "OPEN"}.get(data["outcome"], "FAIL")
                self.attempts.append(f"{data['model']}[{mark}]")
            return
        print(f"    {stage:<10} {self._fmt(stage, data)}")

    @staticmethod
    def _fmt(stage: str, d: dict) -> str:
        if stage == "auth":
            return f"tenant={d['tenant']}  plan={d['plan']}"
        if stage == "ratelimit":
            return f"{d['tokens_left']:.2f} / {d['burst']} tokens left in bucket"
        if stage == "route":
            return f"{d['requested']} -> " + " > ".join(d["chain"])
        if stage == "cache":
            return d["result"]
        if stage == "budget":
            return f"reserved ${d['reserved']:.6f} (worst case)   remaining ${d['remaining']:.6f}"
        if stage == "provider":
            return f"{d['model']:<11} @{d['provider']:<6} {d['outcome']}"
        if stage == "commit":
            return f"actual cost ${d['cost']:.6f}   remaining ${d['remaining']:.6f}"
        if stage == "rejected":
            return f"{d['status']} {d['code']}: {d['message']}"
        return str(d)


def ask(client: TestClient, who: str, text: str, label: str, **extra) -> None:
    print(f"\n[{label}] {who:<6} POST /v1/chat  \"{text[:48]}\"")
    body = {"messages": [{"role": "user", "content": text}], **extra}
    key = KEYS.get(who, who)
    r = client.post("/v1/chat", json=body, headers={"Authorization": f"Bearer {key}"})
    if r.status_code == 200:
        data = r.json()
        note = "  (fallback from " + ", ".join(data["fallback_from"]) + ")" if data["fallback_from"] else ""
        print(f"    <- 200  {r.headers['X-Cache']:<4} model={data['model']}{note}")
        print(f"       \"{data['content'][:64]}\"")
    else:
        extra_hdr = f"  Retry-After={r.headers['Retry-After']}s" if "Retry-After" in r.headers else ""
        print(f"    <- {r.status_code}  {r.json()['error']['code']}{extra_hdr}")


def compact(client: TestClient, trace: Trace, who: str, texts: list[str], **extra) -> None:
    trace.verbose = False
    for i, text in enumerate(texts, 1):
        body = {"messages": [{"role": "user", "content": text}], **extra}
        trace.attempts = []
        r = client.post("/v1/chat", json=body, headers={"Authorization": f"Bearer {KEYS[who]}"})
        if r.status_code == 200:
            d = r.json()
            info = f"{' > '.join(trace.attempts):<36} ${d['usage']['cost_usd']:.6f}"
        else:
            hdr = f" Retry-After={r.headers['Retry-After']}s" if "Retry-After" in r.headers else ""
            info = r.json()["error"]["code"] + hdr
        print(f"    #{i}  {who:<6} -> {r.status_code}  {info}")
    trace.verbose = True


def load_test() -> None:
    """200 concurrent requests straight at the service: limits must hold under contention."""
    container = build(clock=FakeClock())
    service, ok, codes = container.service, 0, {}
    req = ChatRequest(messages=[{"role": "user", "content": "ping"}], temperature=0.7)

    def one(_: int) -> str:
        try:
            service.chat(KEYS["acme"], req)
            return "200"
        except GatewayError as exc:
            return str(exc.status)

    with ThreadPoolExecutor(max_workers=32) as pool:
        for status in pool.map(one, range(200)):
            codes[status] = codes.get(status, 0) + 1
    ok = codes.get("200", 0)
    tenant = service.keys.tenant("acme")
    print(f"    200 requests, 32 threads -> " + ", ".join(f"{k}: {v}" for k, v in sorted(codes.items())))
    print(f"    admitted {ok} == burst {tenant.plan.burst}?  {'YES' if ok == tenant.plan.burst else 'NO'}")
    print(f"    spent ${service.budget.spent('acme'):.6f}  <= budget ${tenant.plan.monthly_budget_usd:.2f}")


def main() -> None:
    clock, trace = FakeClock(), Trace()
    container = build(clock=clock, on_event=trace)
    client = TestClient(create_app(container))
    alpha = container.providers["alpha"]

    banner("exe_404.ai  |  28 . Agent Gateway Platform  (MockLLM, fake clock)")

    banner("1. Normal request, then the same request again (cache)")
    ask(client, "acme", "What is a token bucket?", "1a")
    ask(client, "acme", "What is a token bucket?", "1b")

    banner("2. Provider 'alpha' goes down -> fallback, then circuit breaker opens")
    alpha.set_down(True)
    ask(client, "acme", "Analyze the trade-offs of our caching architecture", "2a")
    print("\n    ...three more pro-tier requests while alpha is still down:")
    compact(client, trace, "acme", ["Plan a database migration", "Compare two queue designs",
                                    "Debug this flaky deploy"])
    alpha.set_down(False)
    clock.advance(30)
    print("\n    alpha recovers; after the 30s cooldown the breaker lets a probe through.")

    banner("3. Free plan: burst of 4 requests (burst=3, 6/min)")
    compact(client, trace, "hobby", ["hi one", "hi two", "hi three", "hi four"])

    banner("4. Free plan asks for a model it did not pay for")
    clock.advance(10)
    ask(client, "hobby", "Explain transformers", "4", model="alpha-pro")

    banner("5. Budget hard stop (free plan budget = $0.0012)")
    clock.advance(60)
    compact(client, trace, "hobby", [f"Write a long essay part {n}" for n in range(1, 4)], max_tokens=250)

    banner("6. Wrong API key")
    ask(client, "sk-stolen-9999", "let me in", "6")

    banner("7. Load test: 200 concurrent requests from one tenant")
    load_test()

    banner("8. Usage metering (admin view)  GET /v1/usage?tenant=...")
    admin = {"Authorization": f"Bearer {KEYS['ops']}"}
    print(f"    {'tenant':<7}{'plan':<6}{'reqs':>5}{'cached':>7}{'tokens':>8}{'cost $':>11}{'left $':>11}  rejected")
    for t in ("acme", "hobby"):
        u = client.get(f"/v1/usage?tenant={t}", headers=admin).json()
        rej = ", ".join(f"{k}={v}" for k, v in u["rejected"].items()) or "-"
        print(f"    {t:<7}{u['plan']:<6}{u['requests']:>5}{u['cached_hits']:>7}"
              f"{u['input_tokens'] + u['output_tokens']:>8}{u['cost_usd']:>11.6f}"
              f"{u['budget_remaining_usd']:>11.6f}  {rej}")

    banner("9. Tamper-evident audit log  GET /v1/audit")
    audit = client.get("/v1/audit", headers=admin).json()
    print(f"    {len(audit['entries'])} entries, hash chain verified: {audit['verified']}")
    for e in audit["entries"][:3]:
        print(f"    #{e['seq']:<3} {e['event']:<14} {e['tenant']:<6} hash={e['hash'][:12]}..."
              f"  prev={e['prev_hash'][:12]}...")
    entries = container.service.audit._entries  # simulate an insider editing history
    entries[2]["cost_usd"] = 0.0
    ok, bad = container.service.audit.verify()
    print(f"    after editing entry #3's cost -> verified: {ok}, chain breaks at #{bad}")
    print()

