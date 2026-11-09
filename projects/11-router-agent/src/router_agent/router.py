"""The router: cheap rules first, an LLM classifier second, a fallback when unsure.

    Stage 1  rules      precise regexes; free and instant; only trusted if exactly ONE intent fires
    Stage 2  LLM        few-shot classifier returning {"intent", "confidence", "reason"}
    Policy   threshold  confidence >= threshold -> specialist, otherwise -> fallback

Most production routers look like this: rules catch the obvious traffic cheaply,
the model handles the long tail, and a threshold decides when to ask instead of guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLM, extract_json

FALLBACK = "fallback"

DEFAULT_RULES: dict[str, list[str]] = {
    "billing": [r"\bINV-\d+\b", r"\brefund", r"\bcharged\b", r"\breceipt\b"],
    "tech_support": [r"\bcrash", r"\bpassword\b", r"\blog ?in\b", r"\berror\b", r"\bbug\b"],
    "sales": [r"\bpric(e|ing)\b", r"\bdemo\b", r"\bquote\b", r"\benterprise\b"],
}

CLASSIFY_SYSTEM = """TASK: CLASSIFY
You route customer messages to exactly one team. Choose the best intent from the list,
or "fallback" if none fits or the message clearly needs two teams. Give a calibrated
confidence between 0 and 1 (0.9 = obvious, 0.5 = a coin flip).
Reply with JSON only: {"intent": "...", "confidence": 0.0, "reason": "..."}"""


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    examples: tuple[str, ...]


@dataclass
class RouteDecision:
    intent: str
    confidence: float
    method: str  # rule | llm | fallback
    reason: str
    candidates: list[str] = field(default_factory=list)


class Router:
    def __init__(self, llm: LLM, intents: list[Intent], threshold: float = 0.6,
                 rules: dict[str, list[str]] | None = None) -> None:
        self.llm = llm
        self.intents = {i.name: i for i in intents}
        self.threshold = threshold
        self.rules = {name: [re.compile(p, re.IGNORECASE) for p in patterns]
                      for name, patterns in (DEFAULT_RULES if rules is None else rules).items()}

    @classmethod
    def from_file(cls, llm: LLM, path: str | Path, **kwargs) -> "Router":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        intents = [Intent(name, v["description"], tuple(v["examples"])) for name, v in data.items()]
        return cls(llm, intents, **kwargs)

    # -- stage 1 -------------------------------------------------------------
    def match_rules(self, message: str) -> dict[str, str]:
        """{intent: first matching pattern} for every intent whose rules fire."""
        hits = {}
        for intent, patterns in self.rules.items():
            if hit := next((p.pattern for p in patterns if p.search(message)), None):
                hits[intent] = hit
        return hits

    # -- stage 2 -------------------------------------------------------------
    def classify(self, message: str) -> RouteDecision:
        lines = ["Intents:"]
        for intent in self.intents.values():
            lines.append(f"- {intent.name}: {intent.description}")
            lines += [f"  example ({intent.name}): {ex}" for ex in intent.examples]
        lines.append(f"- {FALLBACK}: anything else, or more than one team needed")
        raw = self.llm.complete(CLASSIFY_SYSTEM, "\n".join(lines) + f"\n\nMessage: {message}")
        try:
            data = extract_json(raw)
            intent, confidence = str(data["intent"]), float(data["confidence"])
        except (ValueError, KeyError, TypeError):
            return RouteDecision(FALLBACK, 0.0, "fallback", "classifier returned unusable output")
        if intent not in self.intents and intent != FALLBACK:
            return RouteDecision(FALLBACK, 0.0, "fallback", f"classifier invented intent {intent!r}")
        return RouteDecision(intent, max(0.0, min(confidence, 1.0)), "llm", str(data.get("reason", "")))

    # -- policy --------------------------------------------------------------
    def route(self, message: str) -> RouteDecision:
        hits = self.match_rules(message)
        if len(hits) == 1:
            (intent, pattern), = hits.items()
            return RouteDecision(intent, 0.95, "rule", f"rule /{pattern}/ matched")
        decision = self.classify(message)
        if len(hits) > 1:
            decision.candidates = sorted(hits)
            decision.reason = f"rules disagree ({', '.join(sorted(hits))}); {decision.reason}"
        if decision.intent == FALLBACK:
            return RouteDecision(FALLBACK, decision.confidence, "fallback", decision.reason, decision.candidates)
        if decision.confidence < self.threshold:
            reason = f"best guess {decision.intent} ({decision.confidence:.2f}) is below threshold {self.threshold}"
            return RouteDecision(FALLBACK, decision.confidence, "fallback", reason, decision.candidates)
        return decision
