"""Eval suite (recap of 15): JSON test cases, small graders, a report and a CI exit code."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from capstone.domain.models import AskResponse

Grader = Callable[[AskResponse, Any], tuple[bool, str]]


def _contains(r: AskResponse, needles: list[str]) -> tuple[bool, str]:
    missing = [n for n in needles if n.lower() not in r.answer.lower()]
    return not missing, f"missing {missing}" if missing else "ok"


def _not_contains(r: AskResponse, needles: list[str]) -> tuple[bool, str]:
    found = [n for n in needles if n.lower() in r.answer.lower()]
    return not found, f"leaked {found}" if found else "ok"


def _cited(r: AskResponse, expected: bool) -> tuple[bool, str]:
    return bool(r.citations) == expected, f"citations={len(r.citations)}"


def _blocked(r: AskResponse, expected: bool) -> tuple[bool, str]:
    return r.blocked == expected, f"blocked={r.blocked}"


def _tools(r: AskResponse, expected: list[str]) -> tuple[bool, str]:
    return set(expected) <= set(r.tools_used), f"used={r.tools_used}"


def _source(r: AskResponse, expected: str) -> tuple[bool, str]:
    sources = [c.source for c in r.citations]
    return expected in sources, f"sources={sources}"


GRADERS: dict[str, Grader] = {"contains": _contains, "not_contains": _not_contains, "cited": _cited,
                              "blocked": _blocked, "tools": _tools, "source": _source}


@dataclass
class CaseResult:
    id: str
    passed: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_suite(ask: Callable[[str], AskResponse], cases: list[dict[str, Any]]) -> list[CaseResult]:
    results = []
    for case in cases:
        response = ask(case["question"])
        checks = [(name, *GRADERS[name](response, expected)) for name, expected in case["expect"].items()]
        results.append(CaseResult(case["id"], all(ok for _, ok, _ in checks), checks))
    return results


def report(results: list[CaseResult]) -> str:
    lines = [f"  {'case':<22} {'result':<6}  checks", "  " + "-" * 70]
    for r in results:
        detail = ", ".join(f"{n}:{'ok' if ok else 'FAIL(' + why + ')'}" for n, ok, why in r.checks)
        lines.append(f"  {r.id:<22} {'PASS' if r.passed else 'FAIL':<6}  {detail}")
    passed = sum(r.passed for r in results)
    lines.append(f"\n  {passed}/{len(results)} passed ({passed / max(1, len(results)):.0%})")
    return "\n".join(lines)
