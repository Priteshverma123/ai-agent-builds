# AI Agent Builds: 30 agentic-AI projects, from your first agent to production multi-agent systems

Original, runnable, heavily explained projects. Every one runs **offline with no API key** (a mock LLM), and each has a
*Build it yourself* tutorial. A new project unlocks every day, with a video on [YouTube @exe_404ai](https://www.youtube.com/@exe_404ai) and [Instagram @exe_404.ai](https://www.instagram.com/exe_404.ai/).

⭐ **Star the repo** to get each new project.

## Quickstart (any project)
```bash
cd projects/01-first-llm-chat-with-memory
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
```
Then follow the project's README.

## The projects
| # | Project | Level | What you build |
|---|---|---|---|
| 01 | ✅ [first-llm-chat-with-memory](projects/01-first-llm-chat-with-memory) | Beginner | A chat CLI with conversation memory and a token-budget window (shows why AI "forgets") |
| 02 | ✅ [tool-calling-from-scratch](projects/02-tool-calling-from-scratch) | Beginner | Function calling with no framework: JSON tool schemas, dispatcher, result feeding |
| 03 | ✅ [react-agent-loop](projects/03-react-agent-loop) | Beginner | The think → act → observe loop with step limits and a readable trace |
| 04 | 🔒 structured-output-extractor (coming soon) | Beginner | Turn messy text (emails, invoices) into validated JSON with pydantic + repair retries |
| 05 | 🔒 rag-from-scratch (coming soon) | Beginner | Chunk → embed (local TF-IDF/hashing vectors) → retrieve → answer with citations |
| 06 | 🔒 web-research-agent (coming soon) | Beginner | Multi-step research over a local corpus "web", with source tracking and a cited brief |
| 07 | 🔒 agent-memory-systems (coming soon) | Intermediate | Short-term buffer + long-term SQLite memory + summarisation + relevance recall |
| 08 | 🔒 mcp-server-from-scratch (coming soon) | Intermediate | A Model Context Protocol server over stdio (JSON-RPC 2.0) exposing tools + resources |
| 09 | 🔒 mcp-client-agent (coming soon) | Intermediate | An agent that launches MCP servers, discovers tools at runtime and uses them |
| 10 | 🔒 planner-executor-agent (coming soon) | Intermediate | Plan-then-execute with re-planning on failure and a plan diff in the trace |
| 11 | 🔒 router-agent (coming soon) | Intermediate | Intent router that dispatches to specialist agents with confidence + fallback |
| 12 | 🔒 evaluator-optimizer (coming soon) | Intermediate | Writer + critic loop with a rubric, scores and stop criteria |
| 13 | 🔒 guardrails-prompt-injection (coming soon) | Intermediate | Input/output guardrails, injection detection in tool results, allow-lists, red-team tests |
| 14 | 🔒 human-in-the-loop-approvals (coming soon) | Intermediate | Risk-scored actions that pause for approval; audit log; resumable runs |
| 15 | 🔒 agent-evals-harness (coming soon) | Intermediate | Task suites, graders (exact, rubric, LLM-judge mock), regression report, CI exit codes |
| 16 | 🔒 agent-tracing-observability (coming soon) | Intermediate | Span-based tracing of model/tool calls, JSONL export, a terminal + HTML trace viewer |
| 17 | 🔒 code-review-agent (coming soon) | Advanced | Reads a unified diff, runs static checks, produces ranked review findings |
| 18 | 🔒 sql-data-analyst-agent (coming soon) | Advanced | Natural language → safe read-only SQL on SQLite, with schema grounding and chart-ready output |
| 19 | 🔒 multi-agent-supervisor (coming soon) | Advanced | Supervisor delegating to researcher / coder / reviewer workers with shared state |
| 20 | 🔒 agent-to-agent-protocol (coming soon) | Advanced | A2A-style agent cards + task delegation between two agents over local HTTP |
| 21 | 🔒 debate-and-consensus (coming soon) | Advanced | Multiple agents argue, a judge aggregates, disagreement is surfaced, not hidden |
| 22 | 🔒 parallel-research-swarm (coming soon) | Advanced | Map-reduce research with asyncio workers, dedup and a merged report |
| 23 | 🔒 browser-automation-agent (coming soon) | Advanced | An agent that drives a (local, simulated) web page via an accessibility tree: observe → act |
| 24 | 🔒 voice-agent-pipeline (coming soon) | Advanced | STT → agent → TTS pipeline with streaming, barge-in and latency budget (mock audio) |
| 25 | 🔒 durable-agent-workflows (coming soon) | Advanced | Long-running agent jobs with checkpoints, retries, idempotency and resume after crash |
| 26 | 🔒 customer-support-agent-prod (coming soon) | Production | FastAPI support agent: orders/refunds tools, policy RAG, escalation, evals, tracing |
| 27 | 🔒 document-intake-fde (coming soon) | Production | FDE-style pipeline: invoices/POs → extraction → validation → reconciliation → ERP mock |
| 28 | 🔒 agent-gateway-platform (coming soon) | Production | Multi-tenant agent API: auth keys, rate limits, cost budgets, caching, model fallback |
| 29 | 🔒 sre-incident-agent (coming soon) | Production | Incident triage over logs/metrics mocks, runbook execution with approvals, postmortem draft |
| 30 | 🔒 enterprise-multi-agent-capstone (coming soon) | Production | Capstone: orchestrator + MCP tools + RAG + guardrails + evals + tracing, docker-compose ready |

MIT licensed. Built by [exe_404.ai](https://www.youtube.com/@exe_404ai).
