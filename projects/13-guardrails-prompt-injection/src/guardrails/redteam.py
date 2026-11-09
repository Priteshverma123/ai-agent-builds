"""Red-team corpus runner: measure the detector like any other classifier.

Each case is labelled `attack` or `benign`. Cases marked `known_gap` are attacks we *expect* to
miss (e.g. non-English). They are reported, not hidden, so nobody mistakes a heuristic for a wall.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .detectors import detect


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    label: str
    technique: str
    known_gap: bool = False


@dataclass
class Outcome:
    case: Case
    score: float
    flagged: bool

    @property
    def correct(self) -> bool:
        return self.flagged == (self.case.label == "attack")


@dataclass
class Report:
    outcomes: list[Outcome]

    def _count(self, label: str, flagged: bool, gaps: bool = False) -> int:
        return sum(1 for o in self.outcomes
                   if o.case.label == label and o.flagged == flagged and o.case.known_gap == gaps)

    @property
    def caught(self) -> int:
        return self._count("attack", True)

    @property
    def missed(self) -> int:
        return self._count("attack", False)

    @property
    def false_positives(self) -> int:
        return self._count("benign", True)

    @property
    def known_gaps_missed(self) -> int:
        return self._count("attack", False, gaps=True)

    @property
    def recall(self) -> float:
        total = self.caught + self.missed
        return self.caught / total if total else 1.0

    def by_technique(self) -> dict[str, tuple[int, int]]:
        table: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for o in self.outcomes:
            table[o.case.technique][0] += int(o.correct)
            table[o.case.technique][1] += 1
        return {k: (v[0], v[1]) for k, v in sorted(table.items())}


def load_cases(path: Path) -> list[Case]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Case(**json.loads(line)) for line in lines if line.strip()]


def run_corpus(cases: list[Case]) -> Report:
    outcomes = []
    for case in cases:
        verdict = detect(case.text)
        outcomes.append(Outcome(case, verdict.score, verdict.flagged))
    return Report(outcomes)
