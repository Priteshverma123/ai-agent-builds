"""The rubric: what "good" means, as weighted criteria scored 1-5.

Two kinds of criteria:
- **check**: deterministic code (word count, required keywords, banned phrases, CTA).
  Cheap, exact, and impossible to argue with. Use them whenever you can.
- **judge**: an LLM grades fuzzy qualities (clarity, audience fit) and explains why.

Every score below 5 comes with actionable feedback, and that feedback is what the
writer receives. A rubric that only says "6/10" gives the writer nothing to fix.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from .llm import LLM, extract_json


@dataclass(frozen=True)
class Brief:
    product: str
    task: str
    audience: str
    facts: tuple[str, ...]
    required_keywords: tuple[str, ...]
    banned_phrases: tuple[str, ...]
    min_words: int
    max_words: int

    @classmethod
    def from_dict(cls, data: dict) -> "Brief":
        return cls(**{k: tuple(v) if isinstance(v, list) else v for k, v in data.items()})

    def to_json(self) -> str:
        return json.dumps(self.__dict__)


@dataclass(frozen=True)
class Score:
    criterion: str
    score: int  # 1..5
    weight: float
    feedback: str = ""

    @property
    def points_lost(self) -> float:
        return self.weight * (5 - self.score)


@dataclass
class Evaluation:
    scores: list[Score] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Weighted average mapped from 1..5 onto 0..100."""
        weight = sum(s.weight for s in self.scores)
        mean = sum(s.weight * s.score for s in self.scores) / weight
        return round((mean - 1) / 4 * 100, 1)

    def feedback(self, top: int | None = None) -> list[str]:
        """Feedback items, most costly first (optionally only the top N)."""
        ranked = sorted((s for s in self.scores if s.score < 5), key=lambda s: s.points_lost, reverse=True)
        return [s.feedback for s in ranked[:top]]

    def by_name(self) -> dict[str, int]:
        return {s.criterion: s.score for s in self.scores}


def words(text: str) -> list[str]:
    return re.findall(r"[\w'`-]+", text)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


JUDGE_SYSTEM = """TASK: JUDGE
You are a strict editor. Score the text from 1 (poor) to 5 (excellent) on each
criterion and give one concrete, actionable fix for any score below 5.
Reply with JSON only: {"<criterion>": {"score": 1-5, "feedback": "..."}}"""

JUDGE_CRITERIA = {
    "clarity": "Short, plain sentences; no sentence over 22 words.",
    "audience": "Speaks to the reader ('you') about their benefit, more than about the team ('we').",
}


class Rubric:
    WEIGHTS = {"length": 1.0, "keywords": 2.0, "no_hype": 1.5, "cta": 1.0, "clarity": 1.5, "audience": 1.0}

    def __init__(self, brief: Brief, judge: LLM) -> None:
        self.brief = brief
        self.judge = judge

    def evaluate(self, text: str) -> Evaluation:
        return Evaluation([self._length(text), self._keywords(text), self._no_hype(text), self._cta(text), *self._judged(text)])

    # -- deterministic checks -------------------------------------------------
    def _score(self, name: str, score: int, feedback: str) -> Score:
        return Score(name, max(1, min(5, score)), self.WEIGHTS[name], feedback if score < 5 else "")

    def _length(self, text: str) -> Score:
        n, lo, hi = len(words(text)), self.brief.min_words, self.brief.max_words
        distance = max(lo - n, n - hi, 0)
        action = f"Cut to at most {hi}" if n > hi else f"Expand to at least {lo}"
        return self._score("length", 5 - math.ceil(distance / 10), f"{action} words (now {n}).")

    def _keywords(self, text: str) -> Score:
        missing = [k for k in self.brief.required_keywords if k.lower() not in text.lower()]
        found = 1 - len(missing) / len(self.brief.required_keywords)
        feedback = " ".join(f"Mention '{k}' (required)." for k in missing)
        return self._score("keywords", round(1 + 4 * found), feedback)

    def _no_hype(self, text: str) -> Score:
        used = [p for p in self.brief.banned_phrases if p.lower() in text.lower()]
        feedback = " ".join(f"Remove hype phrase '{p}'." for p in used)
        return self._score("no_hype", 5 - 2 * len(used), feedback)

    def _cta(self, text: str) -> Score:
        last = sentences(text)[-1] if text.strip() else ""
        return self._score("cta", 5 if last.startswith("Try") else 1, "End with a call to action starting with 'Try'.")

    # -- LLM judge ------------------------------------------------------------
    def _judged(self, text: str) -> list[Score]:
        criteria = "\n".join(f"- {name}: {desc}" for name, desc in JUDGE_CRITERIA.items())
        data = extract_json(self.judge.complete(JUDGE_SYSTEM, f"Criteria:\n{criteria}\n\nText:\n{text}"))
        results = []
        for name in JUDGE_CRITERIA:
            item = data.get(name, {})
            score = int(item.get("score", 1)) if isinstance(item, dict) else 1
            results.append(self._score(name, score, str(item.get("feedback", "")) if isinstance(item, dict) else ""))
        return results
