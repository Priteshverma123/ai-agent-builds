"""The evaluator-optimizer loop: write -> evaluate -> revise with feedback -> repeat.

Stop criteria (whichever comes first):
  1. target reached     - the score is good enough, so stop spending tokens
  2. plateau            - `patience` rounds without improving by `min_delta`
  3. max iterations     - a hard budget, no matter what

We return the *best* draft, not the last one: a revision can make things worse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm import LLM
from .rubric import Brief, Evaluation, Rubric, words
from .trace import Trace

WRITE_SYSTEM = """TASK: WRITE
You are a product copywriter. Write the announcement described in the brief.
Use only the facts given. Reply with the text only."""

REVISE_SYSTEM = """TASK: REVISE
You are a product copywriter revising your draft. Apply every listed fix, change
nothing else, and use only the facts in the brief. Reply with the revised text only."""

COLUMNS = ["length", "keywords", "no_hype", "cta", "clarity", "audience"]


@dataclass
class Attempt:
    iteration: int
    text: str
    evaluation: Evaluation
    fixes_requested: list[str] = field(default_factory=list)


@dataclass
class OptimizeResult:
    best: Attempt
    attempts: list[Attempt]
    stop_reason: str


class EvaluatorOptimizer:
    def __init__(self, writer: LLM, rubric: Rubric, target: float = 90.0, max_iterations: int = 6,
                 patience: int = 2, min_delta: float = 1.0, fixes_per_round: int = 2, trace: Trace | None = None) -> None:
        self.writer = writer
        self.rubric = rubric
        self.target = target
        self.max_iterations = max_iterations
        self.patience = patience
        self.min_delta = min_delta
        self.fixes_per_round = fixes_per_round  # focused feedback beats a wall of comments
        self.trace = trace or Trace(echo=False)

    def run(self, brief: Brief) -> OptimizeResult:
        self.trace.box("EVALUATOR-OPTIMIZER", [
            brief.task, f"target {self.target:.0f}/100 | max {self.max_iterations} iterations | plateau: "
                        f"{self.patience} rounds < +{self.min_delta} | {self.fixes_per_round} fixes per round"])
        self.trace.event("score", "iter  total  " + "  ".join(f"{c[:8]:>8}" for c in COLUMNS) + "   words")

        text = self.writer.complete(WRITE_SYSTEM, f"Brief: {brief.to_json()}").strip()
        attempts: list[Attempt] = []
        best, stale = None, 0
        for iteration in range(1, self.max_iterations + 1):
            evaluation = self.rubric.evaluate(text)
            attempt = Attempt(iteration, text, evaluation)
            attempts.append(attempt)
            self._show_scores(attempt, improved=best is None or evaluation.total > best.evaluation.total)

            if best is None or evaluation.total >= best.evaluation.total + self.min_delta:
                best, stale = attempt, 0
            else:
                stale += 1
            if evaluation.total >= self.target:
                return self._finish(best, attempts, f"target reached ({evaluation.total:.1f} >= {self.target:.0f})")
            if stale >= self.patience:
                return self._finish(best, attempts, f"plateau: no gain of +{self.min_delta} in {self.patience} rounds")
            if iteration == self.max_iterations:
                break

            attempt.fixes_requested = evaluation.feedback(top=self.fixes_per_round)
            self.trace.event("fix", f"writer gets the top {len(attempt.fixes_requested)} issue(s)",
                             [f"- {f}" for f in attempt.fixes_requested])
            prompt = (f"Brief: {brief.to_json()}\n\nDraft:\n{text}\n\nFix these issues (most important first):\n"
                      + "\n".join(f"- {f}" for f in attempt.fixes_requested))
            text = self.writer.complete(REVISE_SYSTEM, prompt).strip()
        return self._finish(best, attempts, f"max iterations ({self.max_iterations}) reached")

    def _show_scores(self, attempt: Attempt, improved: bool) -> None:
        scores = attempt.evaluation.by_name()
        row = f"{attempt.iteration:>4}  {attempt.evaluation.total:5.1f}  " + "  ".join(f"{scores[c]:>8}" for c in COLUMNS)
        self.trace.event("score", f"{row}   {len(words(attempt.text)):>5}" + ("" if improved else "   (no better)"))

    def _finish(self, best: Attempt, attempts: list[Attempt], reason: str) -> OptimizeResult:
        self.trace.blank()
        self.trace.box(f"BEST DRAFT  iteration {best.iteration}  score {best.evaluation.total:.1f}/100",
                       [best.text, "", f"stopped: {reason}"])
        return OptimizeResult(best, attempts, reason)
