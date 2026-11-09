# Video hooks · 14 Human-in-the-Loop Approvals

- **hook:** My agent can refund $1,249, but only if a human says yes.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [model]  step 2: issue_refund(order_id='A-1042', amount=1249.0)
              risk HIGH (60/100)
  [PAUSE]  PAUSED: req-2 needs approval
  [refused] sam -> sam started this run and cannot approve it
  [tool]   issue_refund -> refund rf_0001 of 1249.00 issued for A-1042
  [model]  step 4: close_account(customer_id='C-78', purge_data=True)
              risk CRITICAL (80/100)
  [human-] req-4 rejected by bob
  verify() after someone edits bob's rejection: entry 19 was modified
  ```
- **diagram:** Model proposes -> Risk scorer -> Approval request (paused run) -> Human decision -> Executor + audit log
- **real_world:** A support agent that handles double-charge tickets end to end, but waits for finance before any large refund.
- **try_it:** Add an expiry so approvals older than one hour no longer count.
- **flow_steps:**
  1. `cli.py` builds the agent from disk (`build_agent()`, settings from `config.py`) and `ApprovalAgent.start()` opens a run for sam.
  2. `llm.py`'s planner proposes `issue_refund`, and `risk.py` (`RiskPolicy.assess`) scores it HIGH with readable reasons.
  3. `approvals.py` creates an `ApprovalRequest` bound to the action's fingerprint; `store.py` checkpoints the run and it pauses.
  4. A human runs `approve`; `ApprovalAgent.decide()` enforces the rules (not your own run, a written reason, two people for CRITICAL).
  5. `resume()` reloads the checkpoint and `Executor.run()` re-checks the approval before `actions.py` performs the idempotent refund.
  6. Every step is appended to `audit.py`'s hash-chained log, and `verify()` catches anyone editing bob's rejection.
