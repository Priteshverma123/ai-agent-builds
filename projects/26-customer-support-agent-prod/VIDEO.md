# VIDEO hooks · 26 Production Customer Support Agent

- **hook:** This bot can refund you, but only code decides how much.
- **demo_cmd:** `python run.py demo`
- **demo_output:**
  ```
  +-- trace 66c21b26171147fa (13.3 ms) ------------------------------------------------------+
  | USER    I want a refund for my laptop, order ORD-2001                                    |
  | THINK   Intent 'refund' on ORD-2001: load the order first.                               |
  | TOOL    get_order({"order_id": "ORD-2001"}) -> ok: delivered, total 899.00               |
  | THINK   Request the refund; the policy engine decides the outcome.                       |
  | TOOL    issue_refund({"order_id": "ORD-2001", ...}) -> ok: pending_approval 899.00      |
  | REPLY   Your $899.00 refund for ORD-2001 is above our automatic limit, so a specialist   |
  |         will review it (ticket T-0001). You'll hear back within one business day         |
  | CITE    refunds.md#approvals  (Approvals)                                                |
  POST /queue/T-0001/resolve -> approved by maria, refund R-0002 for $899.00
  ```
- **diagram:** `POST /chat` → `Agent loop (LLM + step budget)` → `Tools (policy engine, orders, RAG)` → `Human queue` → `Trace + evals`
- **real_world:** An online electronics store auto-handles "where's my parcel?" and small refunds, and routes $200+ refunds and angry customers to a human, with a trace for every decision.
- **try_it:** Add a `cancel_order` tool for orders that haven't shipped, then write two eval cases that prove it can't cancel a delivered order.
- **flow_steps:**
  1. `cli.py` runs the demo, which posts each customer message to `POST /chat` in `api.py`; pydantic validates it and `require_key` checks the API key.
  2. `SupportAgent.handle()` in `services/agent.py` loads the conversation (tied to that customer) and starts `_run_loop()` with a step budget from `config.py`.
  3. The LLM (`MockLLM` in `adapters/llm.py`) picks a tool; `SupportTools.execute()` in `services/tools.py` validates the arguments and runs `get_order`, `search_policy` or `issue_refund`.
  4. `issue_refund` asks the pure `evaluate_refund()` in `domain/policy.py`: small refunds are approved, $899 goes to the `HumanQueue` as ticket T-0001.
  5. The final reply passes the `_citations()` guard (only real policy chunks survive) and the whole turn is saved by `TraceStore` in `observability.py`.
  6. A human calls `POST /queue/T-0001/resolve`; `resolve_ticket()` records the refund in the `RefundLedger`, and only then does money move.

