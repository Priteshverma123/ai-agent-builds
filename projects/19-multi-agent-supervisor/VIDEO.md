# VIDEO · 19 Multi-Agent Supervisor

hook: Three AI agents, one boss, and a test suite that decides.

demo_cmd: python demo.py

demo_output:
```text
  STEP 1       | -> researcher x2 in parallel  [llm]
    merge      | research now 5 rules, 5 examples from 2 sources
  STEP 2       | -> coder  [llm]
                 => wrote v1 (3 lines)
  STEP 3       | -> reviewer  [llm]
                 => v1 FAILED 4/6, e.g. slugify('Hello, World!') returned 'hello,-world!'
  STEP 4       | -> coder  [llm]
  STEP 5       | -> reviewer  [llm]
                 => v2 PASSED
| status : APPROVED   (Latest code passed review.)                           |
```

diagram:
1. Goal -> Supervisor (LLM proposes, code validates)
2. Researchers x2 in parallel
3. Coder writes code
4. Reviewer runs the tests
5. Shared state -> merged deliverable

real_world: A dev team bot turns a Jira ticket into a reviewed pull request: one agent reads the docs, one codes,
one runs the tests before anyone is pinged.

try_it: Add a fifth example to slug-examples.md that v2 fails, and watch the supervisor loop until it's fixed (or the budget stops it).

flow_steps:
1. `cli.py` loads settings from `config.py` and `build_team()` wires a researcher, a coder and a reviewer to the supervisor.
2. `supervisor.py` shows the model a five-line `SharedState.summary()`; the model proposes "two researchers in parallel", and `validate()` checks it is allowed.
3. `workers/researcher.py` searches `examples/kb` twice at once; `state.py` merges both results into one set of rules and examples.
4. `workers/coder.py` writes v1, `workers/reviewer.py` runs it against every example and it fails; the failures go back to the coder, who writes v2.
5. The reviewer passes v2, the model says FINISH, and `Supervisor.merge()` only approves because the latest code has a passing review.
