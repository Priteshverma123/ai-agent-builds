# Video hooks · 17 Code Review Agent

- **hook:** A code comment told my AI reviewer to ignore a leaked key.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  [static]  11 findings from 9 rules
  [llm]     added http-no-timeout at shop/api.py:31
  [GUARD]   refused to dismiss CRITICAL hardcoded-secret@shop/api.py:10 ('author says it is a test fixture')
  [GUARD]   dropped LLM finding 'connection-pooling' at shop/db.py:3 (not a changed line)
   1  CRITICAL  0.95  shop/api.py:10           hardcoded-secret       static
   2  CRITICAL  0.90  shop/pricing.py:5        eval-exec              static
   3  HIGH      0.90  shop/db.py:24            sql-injection          static
  +========================= VERDICT: REQUEST_CHANGES =========================+
  ```
- **diagram:** Unified diff -> Parse + rebuild files -> Static checks -> LLM review -> Guard -> Ranked verdict
- **real_world:** Every pull request gets a ranked security and quality review on the exact changed lines within seconds, before a human looks.
- **try_it:** Add a rule that flags `requests` calls with `verify=False` through the AST instead of a regex.
- **flow_steps:**
  1. `cli.py` reads the diff (or stdin) with defaults from `config.py`, and `context.py` rebuilds every changed file via `diff.py`.
  2. `checks/` runs regex rules on added lines, AST rules on the full new file, and project rules like "no tests changed".
  3. `agent.py` sends each file's diff plus the static findings to the model in `llm.py`, which replies in a strict JSON schema.
  4. The guard in `ReviewAgent.review()` drops comments on unchanged lines and refuses to dismiss HIGH/CRITICAL findings, even when a code comment asks.
  5. `findings.py` dedupes and ranks by severity then confidence and picks the verdict; `render.py` prints it as text, Markdown or JSON.
