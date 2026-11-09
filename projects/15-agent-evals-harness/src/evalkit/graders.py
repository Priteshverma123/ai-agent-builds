"""Graders: each turns (output, params) into a score in [0, 1], a pass/fail and a reason.

Use the cheapest grader that measures what you care about:
exact / contains / regex / numeric / json_fields are free and deterministic; rubric combines
several cheap checks with weights; llm_judge is for qualities only a reader can judge (tone,
helpfulness) and is itself a model whose output must be parsed defensively.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from .llm import LLM
from .suite import GraderSpec


@dataclass(frozen=True)
class Grade:
    score: float
    passed: bool
    detail: str


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().strip(".!").casefold()


def exact(output: str, p: dict[str, Any]) -> Grade:
    ok = normalise(output) == normalise(str(p["expected"]))
    return Grade(float(ok), ok, "exact match" if ok else f"expected {p['expected']!r}")


def contains(output: str, p: dict[str, Any]) -> Grade:
    text = output.casefold()
    required, forbidden = p.get("all", []), p.get("none", [])
    missing = [s for s in required if s.casefold() not in text]
    present = [s for s in forbidden if s.casefold() in text]
    checks = len(required) + len(forbidden)
    score = 1.0 if not checks else (checks - len(missing) - len(present)) / checks
    problems = [f"missing {m!r}" for m in missing] + [f"must not say {f!r}" for f in present]
    return Grade(score, not problems, "; ".join(problems) or "all phrases ok")


def regex(output: str, p: dict[str, Any]) -> Grade:
    ok = re.search(p["pattern"], output, re.IGNORECASE) is not None
    return Grade(float(ok), ok, f"/{p['pattern']}/ {'found' if ok else 'not found'}")


def numeric(output: str, p: dict[str, Any]) -> Grade:
    """Compare a number in the output. Answers usually restate the question first ("for 3 items
    it costs 7.99"), so by default the LAST number is the answer; set `pick: "first"` to override."""
    numbers = re.findall(r"-?\d+(?:\.\d+)?", output.replace(",", ""))
    if not numbers:
        return Grade(0.0, False, "no number in output")
    picked = numbers[0] if p.get("pick") == "first" else numbers[-1]
    value, expected, tol = float(picked), float(p["expected"]), float(p.get("tolerance", 0.0))
    ok = abs(value - expected) <= tol
    return Grade(float(ok), ok, f"got {value}, expected {expected} +/- {tol}")


def json_fields(output: str, p: dict[str, Any]) -> Grade:
    match = re.search(r"\{.*\}", output, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return Grade(0.0, False, "output is not a JSON object")
    expected: dict[str, Any] = p["expected"]
    wrong = [k for k, v in expected.items() if data.get(k) != v]
    score = (len(expected) - len(wrong)) / len(expected)
    return Grade(score, not wrong, f"wrong fields: {wrong}" if wrong else "fields match")


RUBRIC_CHECKS: dict[str, Callable[[str, Any], bool]] = {
    "contains": lambda out, arg: arg.casefold() in out.casefold(),
    "not_contains": lambda out, arg: arg.casefold() not in out.casefold(),
    "regex": lambda out, arg: re.search(arg, out, re.IGNORECASE) is not None,
    "max_words": lambda out, arg: len(out.split()) <= int(arg),
}


def rubric(output: str, p: dict[str, Any]) -> Grade:
    total = earned = 0.0
    failed = []
    for criterion in p["criteria"]:
        weight = float(criterion.get("weight", 1.0))
        total += weight
        if RUBRIC_CHECKS[criterion["check"]](output, criterion["arg"]):
            earned += weight
        else:
            failed.append(criterion["name"])
    score = earned / total
    ok = score >= float(p.get("pass_at", 1.0))
    return Grade(round(score, 3), ok, f"failed: {', '.join(failed)}" if failed else "all criteria met")


JUDGE_PROMPT = """You are grading a customer-support reply.
Question: {question}
Reply: {output}
Key points a great reply covers: {key_points}
Score 1-5 (5 = covers every key point, kind and concise).
Answer in exactly this format:
SCORE: <1-5>
REASON: <one sentence>"""


def llm_judge(output: str, p: dict[str, Any], judge: LLM, question: str) -> Grade:
    prompt = JUDGE_PROMPT.format(question=question, output=output, key_points="; ".join(p["key_points"]))
    reply = judge.complete("You are a strict, consistent grader.", [{"role": "user", "content": prompt}])
    match = re.search(r"SCORE:\s*([1-5])", reply)
    if not match:
        return Grade(0.0, False, f"unparseable judge reply: {reply[:40]!r}")
    stars = int(match.group(1))
    reason = re.search(r"REASON:\s*(.+)", reply)
    ok = stars >= int(p.get("min_score", 4))
    return Grade((stars - 1) / 4, ok, f"judge {stars}/5: {reason.group(1).strip() if reason else ''}")


SIMPLE: dict[str, Callable[[str, dict[str, Any]], Grade]] = {
    "exact": exact, "contains": contains, "regex": regex, "numeric": numeric,
    "json_fields": json_fields, "rubric": rubric,
}


def grade(spec: GraderSpec, output: str, *, judge: LLM, question: str) -> Grade:
    if spec.type == "llm_judge":
        return llm_judge(output, spec.params, judge, question)
    return SIMPLE[spec.type](output, spec.params)
