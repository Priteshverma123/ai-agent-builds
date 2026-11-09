# Video hooks · 16 Agent Tracing & Observability

- **hook:** See every thought, tool call and cent your agent spends.
- **demo_cmd:** `python demo.py`
- **demo_output:**
  ```
  TRACE 000000000000000b  "Find the latest news about solar batteries."
    total 2,767 ms | llm 2 calls 887 ms | tools 2 calls 1,880 ms | tokens 147 in / 43 out | $0.0014 | errors 1
    agent.run                           0    2767  |##################################|
      step 1                            0    2256  |############################      |
        llm mock-llm                    0     376  |#####                             |
        tool search                   376    1500  |    !!!!!!!!!!!!!!!!!!            |
          * exception: TimeoutError search backend did not answer within 1500 ms
        tool search                  1876     380  |                       #####      |
    slowest: tool search (1500 ms)
  ```
- **diagram:** Agent loop -> TracedLLM / TracedTools -> Tracer (spans) -> trace.jsonl -> Terminal + HTML viewer
- **real_world:** When a user says "the bot was slow and wrong", open the trace and see the tool that timed out and what the model saw.
- **try_it:** Add a latency budget that marks any model call over 500 ms in red.
- **flow_steps:**
  1. `cli.py` loads settings from `config.py` and `run_demo()` builds a `Tracer` on a simulated clock with a `JSONLExporter`.
  2. `agent.py`'s `Agent.run()` opens an `agent.run` span and one `step` span per loop; the agent itself has almost no tracing code.
  3. `instrument.py` does the work: `TracedLLM` records tokens and cost, `TracedTools` records args, results and the search timeout.
  4. `spans.py` nests every span under its parent via a ContextVar, redacts secrets, and hands each finished span to the exporter.
  5. `exporters.py` reads `out/trace.jsonl` back, and `viewer_terminal.py` and `viewer_html.py` draw the waterfall from the export alone.
