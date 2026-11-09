# Video hooks · 15 Agent Evals Harness

- **hook:** The friendlier prompt broke three answers. CI caught all three.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  refund_window           0.00  REGRESSED  missing '30 days'
  shipping_cost           0.00  REGRESSED  got 9.49, expected 7.99 +/- 0.01
  broken_package          0.75  REGRESSED  failed: under 60 words
  angry_customer          1.00  FIXED
  pass rate 70%   mean score 0.775   agent mock:support-v2
  vs baseline: 3 regressed, 1 fixed, score -0.125, pass rate -20%
  GATE: REGRESSION (exit code 1)
    - 3 case(s) regressed: refund_window, shipping_cost, broken_package
  ```
- **diagram:** Suite JSON -> Runner (agent x trials) -> Graders -> Compare with baseline -> Exit code
- **real_world:** Every prompt or model change to a support bot runs the suite in CI and is blocked if any answer gets worse.
- **try_it:** Add a case that v1 fails, fix the bot, then save a new baseline.
- **flow_steps:**
  1. `cli.py` reads the suite, baseline and output paths from `config.py`, and `suite.py` validates the suite JSON with pydantic.
  2. `runner.py` (`run_suite`) sends every case to `agent.py`'s `SupportAgent`, which may call its `order_status` tool.
  3. `graders.py` scores each answer: exact, contains, numeric, JSON and rubric checks, plus `llm_judge` for tone.
  4. `compare.py` lines the run up against `examples/baseline.json` and lists regressions and fixes.
  5. `gate()` turns that into exit code 0, 1 or 2, and `report.py` prints the table and writes a Markdown report for CI.
