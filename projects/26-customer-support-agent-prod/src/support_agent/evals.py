"""Eval suite: realistic support conversations with explicit pass/fail expectations.

Each case runs against a fresh agent (fresh ledger, queue and conversation store), so cases are
independent and the suite can gate a deploy: exit code 1 if anything fails.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .adapters.llm import LLM
from .bootstrap import build_agent
from .config import Settings
from .services.agent import TurnResult

DEMO_TODAY = date(2026, 10, 20)


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(expect: dict[str, Any], results: list[TurnResult]) -> list[str]:
    """Compare what happened with what the case expects. Returns human-readable failures."""
    failures: list[str] = []
    tools = [t for r in results for t in r.tools]
    names = [t.name for t in tools]
    final = results[-1]
    for name in expect.get("tools_include", []):
        if name not in names:
            failures.append(f"expected tool {name}, got {names}")
    for name in expect.get("tools_exclude", []):
        if name in names:
            failures.append(f"tool {name} must not be called")
    if "refund_status" in expect:
        refunds = [t.summary.split()[0] for t in tools if t.name == "issue_refund" and t.ok]
        if not refunds or refunds[-1] != expect["refund_status"]:
            failures.append(f"refund_status {refunds[-1] if refunds else None!r} != {expect['refund_status']!r}")
    if "escalated" in expect and final.escalated != expect["escalated"]:
        failures.append(f"escalated={final.escalated}, expected {expect['escalated']}")
    for needle in expect.get("reply_contains", []):
        if needle.lower() not in final.reply.lower():
            failures.append(f"reply missing {needle!r}")
    if len(final.citations) < expect.get("min_citations", 0):
        failures.append(f"expected >= {expect['min_citations']} citation(s), got {len(final.citations)}")
    return failures


def run_case(case: dict[str, Any], settings: Settings, llm: LLM | None = None) -> EvalResult:
    agent = build_agent(settings, llm)
    results: list[TurnResult] = []
    conversation_id = None
    for turn in case["turns"]:
        result = agent.handle(case["customer_id"], turn, conversation_id)
        conversation_id = result.conversation_id
        results.append(result)
    failures = check(case["expect"], results)
    return EvalResult(case["id"], not failures, failures, [t.name for r in results for t in r.tools])


def run_suite(settings: Settings, llm: LLM | None = None) -> list[EvalResult]:
    return [run_case(c, settings, llm) for c in load_cases(settings.data_dir / "evals.json")]


def format_report(results: list[EvalResult]) -> str:
    width = max(len(r.case_id) for r in results)
    rule = "+" + "-" * (width + 52) + "+"
    lines = [rule, f"| {'case':<{width}}  {'result':<6}  {'tools':<41}|", rule]
    for r in results:
        tools = ",".join(r.tools)[:40]
        lines.append(f"| {r.case_id:<{width}}  {'PASS' if r.passed else 'FAIL':<6}  {tools:<41}|")
        lines.extend(f"|   - {f[:width + 47]:<{width + 47}}|" for f in r.failures)
    passed = sum(r.passed for r in results)
    lines.append(rule)
    lines.append(f"  {passed}/{len(results)} passed ({100 * passed / len(results):.0f}%)")
    return "\n".join(lines)
