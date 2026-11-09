"""Compare a run with a baseline and decide the CI exit code.

Averages hide regressions: v2 can fix one case and break three and still look "about the same".
So the gate looks at **case flips** first, then at the overall score, then at the absolute bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .runner import RunResult


class Exit(IntEnum):
    OK = 0
    REGRESSION = 1
    BELOW_THRESHOLD = 2


@dataclass
class Comparison:
    regressions: list[str] = field(default_factory=list)  # passed in baseline, fails now
    fixes: list[str] = field(default_factory=list)  # failed in baseline, passes now
    new_cases: list[str] = field(default_factory=list)
    score_delta: float = 0.0
    pass_rate_delta: float = 0.0


@dataclass
class GateResult:
    exit: Exit
    reasons: list[str]
    comparison: Comparison | None


def compare(current: RunResult, baseline: RunResult) -> Comparison:
    before = {c.id: c for c in baseline.cases}
    result = Comparison(
        score_delta=round(current.mean_score - baseline.mean_score, 4),
        pass_rate_delta=round(current.pass_rate - baseline.pass_rate, 4),
    )
    for case in current.cases:
        old = before.get(case.id)
        if old is None:
            result.new_cases.append(case.id)
        elif old.passed and not case.passed:
            result.regressions.append(case.id)
        elif not old.passed and case.passed:
            result.fixes.append(case.id)
    return result


def gate(current: RunResult, baseline: RunResult | None, pass_threshold: float,
         score_tolerance: float = 0.02) -> GateResult:
    reasons: list[str] = []
    comparison = compare(current, baseline) if baseline else None
    if comparison and comparison.regressions:
        reasons.append(f"{len(comparison.regressions)} case(s) regressed: {', '.join(comparison.regressions)}")
    if comparison and comparison.score_delta < -score_tolerance:
        reasons.append(f"mean score dropped {comparison.score_delta:+.3f} (tolerance {score_tolerance})")
    if reasons:
        return GateResult(Exit.REGRESSION, reasons, comparison)
    if current.pass_rate < pass_threshold:
        return GateResult(Exit.BELOW_THRESHOLD,
                          [f"pass rate {current.pass_rate:.0%} below threshold {pass_threshold:.0%}"], comparison)
    return GateResult(Exit.OK, ["no regressions, threshold met"], comparison)
