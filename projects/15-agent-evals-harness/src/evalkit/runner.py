"""Run a suite against an agent and collect per-case, per-grader results."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .agent import SupportAgent
from .graders import Grade, grade
from .llm import LLM
from .suite import Suite


@dataclass
class CaseResult:
    id: str
    tags: list[str]
    output: str
    score: float  # weighted mean of grader scores, in [0, 1]
    passed: bool  # every grader passed in every trial
    pass_count: int  # trials that passed
    trials: int
    latency_ms: float
    grades: list[dict[str, Any]] = field(default_factory=list)

    @property
    def flaky(self) -> bool:
        return 0 < self.pass_count < self.trials


@dataclass
class RunResult:
    suite: str
    suite_version: str
    agent: str
    cases: list[CaseResult]

    @property
    def pass_rate(self) -> float:
        return sum(c.passed for c in self.cases) / len(self.cases)

    @property
    def mean_score(self) -> float:
        return sum(c.score for c in self.cases) / len(self.cases)

    def by_tag(self) -> dict[str, tuple[int, int]]:
        tags: dict[str, list[int]] = {}
        for c in self.cases:
            for t in c.tags:
                tags.setdefault(t, [0, 0])
                tags[t][0] += int(c.passed)
                tags[t][1] += 1
        return {t: (v[0], v[1]) for t, v in sorted(tags.items())}

    def to_dict(self) -> dict[str, Any]:
        return {"suite": self.suite, "suite_version": self.suite_version, "agent": self.agent,
                "pass_rate": round(self.pass_rate, 4), "mean_score": round(self.mean_score, 4),
                "cases": [asdict(c) for c in self.cases]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunResult":
        return cls(data["suite"], data["suite_version"], data["agent"], [CaseResult(**c) for c in data["cases"]])


def run_suite(suite: Suite, agent: SupportAgent, judge: LLM, trials: int = 1) -> RunResult:
    results = []
    for case in suite.cases:
        scores, passes, grades, latency, output = [], 0, [], 0.0, ""
        for _ in range(trials):
            started = time.perf_counter()
            output = agent.run(case.input).answer
            latency += (time.perf_counter() - started) * 1000
            trial: list[tuple[float, Grade]] = [
                (spec.weight, grade(spec, output, judge=judge, question=case.input)) for spec in case.graders
            ]
            total_weight = sum(w for w, _ in trial)
            scores.append(sum(w * g.score for w, g in trial) / total_weight)
            passes += all(g.passed for _, g in trial)
            grades = [{"type": spec.type, **asdict(g)} for spec, (_, g) in zip(case.graders, trial)]
        results.append(CaseResult(
            id=case.id, tags=case.tags, output=output, score=round(sum(scores) / trials, 4),
            passed=passes == trials, pass_count=passes, trials=trials,
            latency_ms=round(latency / trials, 2), grades=grades,
        ))
    return RunResult(suite.name, suite.version, agent.name, results)
