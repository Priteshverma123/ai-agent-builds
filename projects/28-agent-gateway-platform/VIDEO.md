# VIDEO · 28 Agent Gateway Platform

**hook:** 200 requests hit at once. Exactly 10 get through.

**demo_cmd:** `python demo.py`

**demo_output:**
```
[1a] acme   POST /v1/chat  "What is a token bucket?"
    ratelimit  9.00 / 10 tokens left in bucket
    route      auto -> alpha-fast > beta-fast
    budget     reserved $0.000235 (worst case)   remaining $4.999765
    provider   alpha-fast  @alpha  ok
    #3  acme   -> 200  alpha-pro[OPEN] > beta-pro[ok]       $0.000677
    #3  hobby  -> 402  budget_exceeded
    200 requests, 32 threads -> 200: 10, 429: 190
    after editing entry #3's cost -> verified: False, chain breaks at #3
```

**diagram:** API key → Rate limit (token bucket) → Router + cache → Budget reserve → Provider fallback → Meter + audit

**real_world:** A SaaS company resells AI features: free users get 6 requests/min and $0.001, enterprise customers get their own bill, and an OpenAI outage fails over to Anthropic automatically.

**try_it:** Make the cache semantic, so "What's a token bucket?" hits the cache for "what is a token bucket".

**flow_steps:**
1. `api/app.py` receives `POST /v1/chat`; `GatewayService.chat()` in `services/gateway.py` asks `KeyStore` (`adapters/keystore.py`) which tenant owns the API key, and rejects unknown keys before anything is spent.
2. `RateLimiter.acquire()` in `services/ratelimit.py` takes one token from the tenant's bucket; an empty bucket means 429 with `Retry-After`.
3. `ModelRouter.route()` in `services/router.py` picks a fast or pro model the plan allows, and `ResponseCache` (`services/cache.py`) answers repeats for free.
4. `BudgetLedger.reserve()` in `services/budget.py` holds the worst-case cost, then `call_with_fallback()` tries alpha, skips it when the `CircuitBreaker` is open, and falls back to beta.
5. The real cost is committed, `UsageMeter` records tokens and dollars, and `AuditLog` (`services/audit.py`) appends a hash-chained entry that exposes any later edit.

