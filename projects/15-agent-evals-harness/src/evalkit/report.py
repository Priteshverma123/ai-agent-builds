"""Terminal and Markdown reports."""

from __future__ import annotations

from .compare import Exit, GateResult
from .runner import RunResult

WIDTH = 78


def banner(title: str) -> str:
    return f"+-- {title} " + "-" * max(0, WIDTH - len(title) - 6) + "+"


def _status(case_id: str, passed: bool, gate: GateResult | None) -> str:
    comparison = gate.comparison if gate else None
    if comparison and case_id in comparison.regressions:
        return "REGRESSED"
    if comparison and case_id in comparison.fixes:
        return "FIXED"
    return "pass" if passed else "fail"


def results_table(run: RunResult, gate: GateResult | None = None) -> str:
    rows = [f"  {'case':<22} {'score':>5}  {'status':<10} why", "  " + "-" * (WIDTH - 2)]
    for c in run.cases:
        failing = [g["detail"] for g in c.grades if not g["passed"]]
        why = (failing[0] if failing else "")[:34]
        flaky = " (flaky)" if c.flaky else ""
        rows.append(f"  {c.id:<22} {c.score:>5.2f}  {_status(c.id, c.passed, gate):<10} {why}{flaky}")
    return "\n".join(rows)


def summary(run: RunResult, gate: GateResult) -> str:
    tags = "  ".join(f"{t} {p}/{n}" for t, (p, n) in run.by_tag().items())
    lines = [f"  pass rate {run.pass_rate:.0%}   mean score {run.mean_score:.3f}   agent {run.agent}",
             f"  by tag: {tags}"]
    if gate.comparison:
        c = gate.comparison
        lines.append(f"  vs baseline: {len(c.regressions)} regressed, {len(c.fixes)} fixed, "
                     f"score {c.score_delta:+.3f}, pass rate {c.pass_rate_delta:+.0%}")
    verdict = "PASS" if gate.exit is Exit.OK else gate.exit.name
    lines.append(f"  GATE: {verdict} (exit code {int(gate.exit)})")
    lines.extend(f"    - {r}" for r in gate.reasons)
    return "\n".join(lines)


def markdown(run: RunResult, gate: GateResult) -> str:
    verdict = "PASS" if gate.exit is Exit.OK else gate.exit.name
    out = [f"# Eval report: {run.suite} v{run.suite_version}", "",
           f"**Agent:** `{run.agent}`  **Gate:** {verdict} (exit {int(gate.exit)})  "
           f"**Pass rate:** {run.pass_rate:.0%}  **Mean score:** {run.mean_score:.3f}", ""]
    out += [f"- {r}" for r in gate.reasons] + ["", "| case | score | status | output |", "|---|---|---|---|"]
    for c in run.cases:
        output = c.output.replace("|", "\\|").replace("\n", " ")[:80]
        out.append(f"| {c.id} | {c.score:.2f} | {_status(c.id, c.passed, gate)} | {output} |")
    return "\n".join(out) + "\n"
