# Conventions for every project in ai-agent-builds

These 30 projects are one curriculum, from a first tool-calling agent to a production multi-agent system.
They must read like the work of one careful engineering team.

## Layout
```
projects/NN-kebab-name/
  README.md          # see "README" below
  requirements.txt   # pinned; only what's needed (stdlib first)
  .env.example       # only if a real provider is optional
  src/<package>/     # the code (or a single module for tiny projects)
  tests/             # >= 3 fast tests, all pass offline
  examples/          # sample inputs/data the demo uses
  Makefile or run.ps1/run.sh optional
```

## Hard rules
- **Original code only.** Never copy code from other repositories or products. Architecture ideas may be inspired by
  public docs or by our REA notes (`research/`), and must be credited in "How it works".
- **Runs offline with no API key.** Every project ships a deterministic `MockLLM` (scripted or rule-based) used by default
  and by the tests. A real provider is optional via env vars (`LLM_PROVIDER=anthropic|openai`, `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`). Never hard-code keys. Never commit `.env`.
- **Python 3.11+.** Allowed deps (already installed in the shared venv): `pydantic`, `fastapi`, `uvicorn`, `httpx`,
  `pytest`. Anything else: prefer the stdlib. Do not `pip install` anything new.
- **Tests:** `python -m pytest -q` from the project folder must pass in < 30 s with no network.
- **Demo command:** one copy-paste command that prints a readable, *teaching* trace (what the agent thought, which tool
  it called, what came back). The trace is what the YouTube video shows, so make it beautiful in a terminal
  (simple ASCII boxes, aligned columns, no colour libraries required).
- Type hints, small functions, docstrings where they teach. No dead code, no TODOs.
- No git commands. Write only inside your own project folders.

## README (this is what learners read; make it excellent)
1. `# NN · Title`. Then a one-line promise ("Build X that does Y in ~N lines").
2. **Level:** Beginner / Intermediate / Advanced / Production. **You'll learn:** 3–5 bullets.
3. **Why this matters.** A real-world example (a business, a job, a daily-life use).
4. **Architecture.** A Mermaid diagram plus 3–6 sentences.
5. **Quickstart.** Exact commands for Windows (PowerShell) and macOS/Linux: venv, install, run demo, run tests.
   Show the expected demo output (shortened).
6. **How it works.** Walk through the key code with short excerpts.
7. **Build it yourself.** A numbered step-by-step tutorial (5–10 steps) that lets a learner re-create the project from an
   empty folder. Each step says what to write and why.
8. **Use a real LLM.** How to switch from MockLLM to a provider.
9. **Production notes / pitfalls.** 3–6 bullets (cost, latency, security, evals).
10. **Extend it.** 3 ideas, plus "Next project: NN+1".
11. Footer: `Part of [AI Agent Builds](../../README.md) by [exe_404.ai](https://www.youtube.com/@exe_404ai) — one agentic-AI project a day.`

## Video hooks (put these in `VIDEO.md` in each project; the video writer uses them)
- `hook`: one surprising line (≤ 12 words) about what this project does.
- `demo_cmd`: the exact command shown on screen.
- `demo_output`: 6–10 lines of the real demo output to show in the terminal scene.
- `diagram`: 3–5 boxes for the architecture flow.
- `real_world`: one concrete real-life use case.
- `try_it`: one-sentence challenge for viewers.
