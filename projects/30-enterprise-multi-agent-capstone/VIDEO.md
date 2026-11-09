# VIDEO · 30 Enterprise Multi-Agent Capstone

**hook:** 29 projects, one request: watch them all fire.

**demo_cmd:** `python demo.py`

**demo_output:**
```
    request ask
      guard   input  allowed=True
      plan    plan  steps=research > analyst > writer
      agent   research  tools=search_docs
        tool    search_docs  args={'query': "I'm staying in Berlin for 3 night
      agent   analyst  tools=calculate
        tool    calculate  args={'expression': '180 * 3'} result={'expression'
    ... your trip that comes to $540 (180 * 3) [1].
        guard   tool-output [quarantined]  chunk=vendor_faq.md#2
    11/11 passed
```

**diagram:** Input guard → Orchestrator plan → Specialists via MCP tools (+RAG) → Output guard → Trace + evals

**real_world:** An internal company assistant answers expense and on-call questions from the handbook with sources and opens Ops tickets, while a poisoned vendor doc can't hijack it.

**try_it:** Add a seventh handbook page and an eval case for it, then make `python run_evals.py` go green.

**flow_steps:**
1. `demo.py` calls `cli.main()`; `container.build()` reads `config.Settings`, indexes the handbook (`services/rag.py`) and starts the MCP tool server, and the demo discovers the tools over `POST /mcp`.
2. A question hits `POST /ask` in `api/app.py`; `Orchestrator.ask()` (`services/orchestrator.py`) runs `guardrails.check_input()` to block injections and redact PII.
3. The LLM (`adapters/llm.py`) plans the specialists: research, analyst, writer. Each agent in `services/agents.py` can call only its own tools through `ScopedTools` and JSON-RPC (`adapters/mcp.py`).
4. `ResearchAgent` searches the docs and quarantines the poisoned vendor chunk; `AnalystAgent` calls `calculate` for 180 x 3 = 540.
5. `WriterAgent` writes the cited answer, `guardrails.check_output()` checks it, and `TraceStore` saves every span so `/traces/{id}` can replay the request.
6. `services/evals.py` runs the 11 eval cases, the same gate CI uses through `python run_evals.py`.

