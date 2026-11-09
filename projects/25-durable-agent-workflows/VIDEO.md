# VIDEO · 25 Durable Agent Workflows

hook: We kill this AI agent mid-job. The customer still gets one email.

demo_cmd: python demo.py

demo_output:
```text
  [worker-1] STEP   | draft_email    done (attempt 1) -> journaled
  [worker-1] CRASH  | send_email     worker dies after the side effect, before the commit
  worker-1 exited with code 137 (killed)
  [worker-2] REPLAY | summarize      result from journal, not re-executed
  [worker-2] REPLAY | draft_email    result from journal, not re-executed
  [worker-2] STEP   | send_email     done (attempt 1) -> journaled
  [worker-2] DEDUP  | email service recognised the idempotency key -> original receipt msg-..., no second email
| LLM calls made by worker-2: 0 (all model outputs replayed from journal)    |
| exactly-once effects: YES                                                  |
```

diagram:
1. Workflow code: await ctx.step(...)
2. Journal check: replay or execute
3. Execute with idempotency key + retries
4. Commit result to SQLite journal
5. Lease lets a new worker resume after a crash

real_world: A billing agent that issues refunds overnight survives a deploy mid-run without refunding anyone twice.

try_it: Remove the idempotency_key check in world.send_email and run the demo again. Count the emails.

flow_steps:
1. `demo.py` calls `cli.main()`; `cli.story()` loads `config.Settings` and `Engine.start()` writes a new run to the SQLite `Journal` (`store.py`).
2. A real subprocess (`cli.worker`) runs `weekly_digest` in `workflows.py`; every action goes through `Context.step()` in `engine.py`, which retries the flaky ticket API and commits each result to the journal.
3. `CrashPlan` kills worker-1 with exit code 137 right after `World.send_email` (`world.py`) and before the commit: the email went out, the journal never heard.
4. Worker-2 calls `Engine.run_when_free()`, waits for the dead worker's lease to expire, and replays `fetch_tickets`, `summarize` and `draft_email` from the journal: zero LLM calls.
5. `send_email` re-runs with the same idempotency key `run_id/send_email`; the email service returns the original receipt, so no second email is sent.
6. `update_crm` finishes, `Journal.finish()` closes the run, and ACT 4 proves exactly one email and one CRM note.
