# Architecture · 12 Evaluator-Optimizer

## Components

| Component | File | Responsibility |
|---|---|---|
| CLI | `src/eval_optimizer/cli.py` | `--brief`; builds the LLM, `Rubric` and `EvaluatorOptimizer` from settings and runs it |
| Settings | `src/eval_optimizer/config.py` | `LLM_PROVIDER`, `LLM_MODEL`, `OPT_TARGET`, `OPT_MAX_ITERATIONS`, `OPT_PATIENCE`, `OPT_MIN_DELTA`, `OPT_FIXES_PER_ROUND`, `OPT_BRIEF_FILE` |
| `EvaluatorOptimizer` | `src/eval_optimizer/optimizer.py` | Write → evaluate → revise loop with three stop criteria; returns the best attempt |
| `Rubric` | `src/eval_optimizer/rubric.py` | Weighted 1–5 criteria: code checks (`length`, `keywords`, `no_hype`, `cta`) + LLM judge (`clarity`, `audience`) |
| `Evaluation` / `Score` | `src/eval_optimizer/rubric.py` | 0–100 total, feedback ranked by points lost |
| `Brief` | `src/eval_optimizer/rubric.py` | Task, facts, required keywords, banned phrases, word range (from `examples/brief.json`) |
| LLMs | `src/eval_optimizer/llm.py` | `MockLLM` (WRITE / REVISE / JUDGE), Anthropic/OpenAI clients, `make_llm()` |
| `Trace` | `src/eval_optimizer/trace.py` | ASCII boxes and `[tag]` events (the score table) |

## Data flow

The writer produces a first draft from the brief. Each iteration the rubric scores the draft: deterministic checks
are exact and free, the judge model grades the fuzzy criteria and explains any score below 5. If no stop criterion
fires, the writer gets only the **top `fixes_per_round`** issues, ranked by weighted points lost, and revises. The loop
tracks the best attempt so far and returns it, because a revision can make things worse.

## One full request

```mermaid
sequenceDiagram
    autonumber
    participant CLI as cli.main
    participant O as EvaluatorOptimizer.run
    participant W as MockLLM (writer)
    participant R as Rubric.evaluate
    participant J as MockLLM (judge)
    CLI->>O: run(brief)
    O->>W: complete(WRITE_SYSTEM, brief)
    W-->>O: draft v1
    loop until target / plateau / max_iterations
        O->>R: evaluate(text)
        R->>R: _length, _keywords, _no_hype, _cta (code checks)
        R->>J: complete(JUDGE_SYSTEM, criteria + text)
        J-->>R: {"clarity": {score, feedback}, "audience": {...}}
        R-->>O: Evaluation(scores) -> total 0..100
        O->>O: _show_scores(); update best / stale counter
        alt total >= target or stale >= patience
            O-->>CLI: _finish(best) -> OptimizeResult
        else
            O->>O: evaluation.feedback(top=fixes_per_round)
            O->>W: complete(REVISE_SYSTEM, brief + draft + fixes)
            W-->>O: revised draft
        end
    end
```

## Design decisions

- **Code checks before judges.** Word count, keywords, banned phrases and the CTA are verified by code: exact, cheap,
  and impossible for a model to argue with. The LLM judge is used only for genuinely fuzzy qualities.
- **Actionable feedback.** Every score below 5 carries a concrete fix; a bare number gives the writer nothing to do.
- **Focused feedback.** Only the most costly issues are sent each round, which converges faster than a wall of comments.
- **Three stop criteria.** Target (good enough), plateau (not improving), max iterations (hard budget).
- **Best, not last.** The result is the highest-scoring attempt.

## Failure modes and handling

| Failure | Handling |
|---|---|
| Judge returns malformed JSON fields | Missing/invalid criterion scores 1 instead of crashing |
| Judge returns no JSON at all | `extract_json()` raises `ValueError` (surfaced, never silently passed) |
| Writer ignores feedback | Plateau stop after `patience` rounds; best draft kept |
| A revision regresses | Best attempt is returned, not the last |
| Target unreachable | `max_iterations` caps cost |
| Same model writes and judges (self-preference bias) | Documented; inject a different `judge` LLM into `Rubric` |

## How to extend

- **Separate judge:** pass a second `make_llm(...)` instance (e.g. a different provider) as `Rubric(judge=...)`.
- **New criterion:** add a weight in `Rubric.WEIGHTS` and a `_check` method or a `JUDGE_CRITERIA` entry.
- **Pairwise judging:** ask the judge "A or B?" between best and new draft to reduce score drift.
- **Eval set:** run several briefs and track the average final score per prompt version.
