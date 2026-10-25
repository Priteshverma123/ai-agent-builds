# The 30 projects (release order = difficulty)

| # | Folder | Level | What it is |
|---|---|---|---|
| 01 | 01-first-llm-chat-with-memory | Beginner | A chat CLI with conversation memory and a token-budget window (shows why AI "forgets") |
| 02 | 02-tool-calling-from-scratch | Beginner | Function calling with no framework: JSON tool schemas, dispatcher, result feeding |
| 03 | 03-react-agent-loop | Beginner | The think → act → observe loop with step limits and a readable trace |
| 04 | 04-structured-output-extractor | Beginner | Turn messy text (emails, invoices) into validated JSON with pydantic + repair retries |
| 05 | 05-rag-from-scratch | Beginner | Chunk → embed (local TF-IDF/hashing vectors) → retrieve → answer with citations |
| 06 | 06-web-research-agent | Beginner | Multi-step research over a local corpus "web", with source tracking and a cited brief |
| 07 | 07-agent-memory-systems | Intermediate | Short-term buffer + long-term SQLite memory + summarisation + relevance recall |
| 08 | 08-mcp-server-from-scratch | Intermediate | A Model Context Protocol server over stdio (JSON-RPC 2.0) exposing tools + resources |
| 09 | 09-mcp-client-agent | Intermediate | An agent that launches MCP servers, discovers tools at runtime and uses them |
| 10 | 10-planner-executor-agent | Intermediate | Plan-then-execute with re-planning on failure and a plan diff in the trace |
| 11 | 11-router-agent | Intermediate | Intent router that dispatches to specialist agents with confidence + fallback |
| 12 | 12-evaluator-optimizer | Intermediate | Writer + critic loop with a rubric, scores and stop criteria |
| 13 | 13-guardrails-prompt-injection | Intermediate | Input/output guardrails, injection detection in tool results, allow-lists, red-team tests |
| 14 | 14-human-in-the-loop-approvals | Intermediate | Risk-scored actions that pause for approval; audit log; resumable runs |
| 15 | 15-agent-evals-harness | Intermediate | Task suites, graders (exact, rubric, LLM-judge mock), regression report, CI exit codes |
| 16 | 16-agent-tracing-observability | Intermediate | Span-based tracing of model/tool calls, JSONL export, a terminal + HTML trace viewer |
| 17 | 17-code-review-agent | Advanced | Reads a unified diff, runs static checks, produces ranked review findings |
| 18 | 18-sql-data-analyst-agent | Advanced | Natural language → safe read-only SQL on SQLite, with schema grounding and chart-ready output |
| 19 | 19-multi-agent-supervisor | Advanced | Supervisor delegating to researcher / coder / reviewer workers with shared state |
| 20 | 20-agent-to-agent-protocol | Advanced | A2A-style agent cards + task delegation between two agents over local HTTP |
| 21 | 21-debate-and-consensus | Advanced | Multiple agents argue, a judge aggregates, disagreement is surfaced, not hidden |
| 22 | 22-parallel-research-swarm | Advanced | Map-reduce research with asyncio workers, dedup and a merged report |
| 23 | 23-browser-automation-agent | Advanced | An agent that drives a (local, simulated) web page via an accessibility tree: observe → act |
| 24 | 24-voice-agent-pipeline | Advanced | STT → agent → TTS pipeline with streaming, barge-in and latency budget (mock audio) |
| 25 | 25-durable-agent-workflows | Advanced | Long-running agent jobs with checkpoints, retries, idempotency and resume after crash |
| 26 | 26-customer-support-agent-prod | Production | FastAPI support agent: orders/refunds tools, policy RAG, escalation, evals, tracing |
| 27 | 27-document-intake-fde | Production | FDE-style pipeline: invoices/POs → extraction → validation → reconciliation → ERP mock |
| 28 | 28-agent-gateway-platform | Production | Multi-tenant agent API: auth keys, rate limits, cost budgets, caching, model fallback |
| 29 | 29-sre-incident-agent | Production | Incident triage over logs/metrics mocks, runbook execution with approvals, postmortem draft |
| 30 | 30-enterprise-multi-agent-capstone | Production | Capstone: orchestrator + MCP tools + RAG + guardrails + evals + tracing, docker-compose ready |
