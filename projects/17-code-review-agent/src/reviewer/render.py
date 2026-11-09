"""Output formats: a terminal report, a Markdown PR comment and JSON for tools."""

from __future__ import annotations

import json
import textwrap

from .agent import ReviewResult

WIDTH = 78
STAGE = {"parse": "[parse]  ", "static": "[static] ", "llm": "[llm]    ", "guard": "[GUARD]  ", "verdict": "[verdict]"}


def terminal(result: ReviewResult) -> str:
    out = ["Review trace", "-" * WIDTH]
    out += [f"{STAGE.get(stage, stage)} {msg}" for stage, msg in result.log]
    out += ["", f"{'#':>2}  {'severity':<9}{'conf':>5}  {'location':<24} {'rule':<22} src", "-" * WIDTH]
    for i, f in enumerate(result.findings, 1):
        where = f"{f.file}:{f.line}"
        out.append(f"{i:>2}  {f.severity.name:<9}{f.confidence:>5.2f}  {where[-24:]:<24} {f.rule:<22} {f.source}")
        out += textwrap.wrap(f.message + (f"  -> {f.suggestion}" if f.suggestion else ""), WIDTH,
                             initial_indent=" " * 6, subsequent_indent=" " * 6)
    if result.dismissed:
        out += ["", "Dismissed as false positives:"]
        out += [f"  - {f.id}: {reason}" for f, reason in result.dismissed]
    banner = f" VERDICT: {result.verdict} "
    out += ["", "+" + banner.center(WIDTH - 2, "=") + "+"]
    return "\n".join(out)


def markdown(result: ReviewResult) -> str:
    icon = {"REQUEST_CHANGES": "Changes requested", "COMMENT": "Comments", "APPROVE": "Approved"}[result.verdict]
    lines = [f"## Automated review: {icon}", ""]
    lines += [f"> {s}" for s in result.summaries] + [""]
    lines += ["| # | Severity | Location | Finding |", "|---|---|---|---|"]
    for i, f in enumerate(result.findings, 1):
        text = f.message + (f" **Fix:** {f.suggestion}" if f.suggestion else "")
        lines.append(f"| {i} | {f.severity.name} | `{f.file}:{f.line}` | {text.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def as_json(result: ReviewResult) -> str:
    return json.dumps(result.to_dict(), indent=2)
