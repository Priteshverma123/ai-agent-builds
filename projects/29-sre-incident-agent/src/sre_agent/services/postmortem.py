"""Draft a blameless postmortem in Markdown, then lint it for blameful language.

Blameless means: describe what the *system* allowed to happen, never who 'should have known better'.
People act reasonably on the information they had; fix the information and the guardrails.
"""
from __future__ import annotations

import re
from datetime import datetime

from sre_agent.adapters.telemetry import FileTelemetry
from sre_agent.domain.models import TimelineEntry, hhmm
from sre_agent.domain.state import AgentState

BLAMEFUL = re.compile(
    r"\b(fault|blame[ds]?|careless(ness)?|negligen\w*|should have known|human error|stupid|incompetent|"
    r"sloppy|messed up|screwed up|(?:his|her|their) mistake)\b", re.I)

ACTION_ITEMS = {
    "bad_deploy": [
        ("Add a canary stage that compares DB connections and p95 before promoting {service}", "{team}"),
        ("CI check: pool size x max replicas must stay below the database's max_connections", "{team}"),
        ("Alert when {dependency} connections exceed 80% of max_connections", "data-platform"),
        ("Runbook: for regressions within 30 min of a deploy, roll back before restarting", "sre"),
    ],
    "dependency_saturation": [("Capacity review for {dependency}", "data-platform")],
    "traffic_surge": [("Autoscaling policy review for {service}", "{team}")],
}


def lint_blameless(markdown: str) -> list[str]:
    """Return one message per blameful phrase found (empty list = pass)."""
    issues = []
    for n, line in enumerate(markdown.splitlines(), 1):
        for m in BLAMEFUL.finditer(line):
            issues.append(f"line {n}: '{m.group(0)}' - describe the system condition instead")
    return issues


def estimate_impact(telemetry: FileTelemetry, service: str, start: datetime, end: datetime) -> tuple[float, int]:
    """(peak error %, estimated failed requests) between start and end, extrapolating the last sample."""
    err, rps = telemetry.series(f"{service}.error_rate_pct"), telemetry.series(f"{service}.requests_per_s")
    minutes = int((end - start).total_seconds() // 60)
    first = int((start - err.start).total_seconds() // 60)
    failed = 0.0
    for m in range(first, first + minutes):
        i = min(m, len(err.values) - 1)
        failed += rps.values[i] * 60 * err.values[i] / 100
    return max(err.values[first:]), int(failed)


def severity(peak_error_pct: float) -> str:
    return "SEV1" if peak_error_pct >= 25 else "SEV2" if peak_error_pct >= 5 else "SEV3"


def render(state: AgentState, timeline: list[TimelineEntry], telemetry: FileTelemetry,
           summary: str, resolved_at: datetime) -> str:
    first, h = state.first_anomaly, state.top_hypothesis
    if first is None or h is None:
        return f"# Postmortem: {state.alert.id}\n\nNo sustained anomaly was found; alert tuning recommended.\n"
    service = first.service
    peak, failed = estimate_impact(telemetry, service, first.start, resolved_at)
    duration = int((resolved_at - first.start).total_seconds() // 60)
    params = {"service": service, "team": telemetry.services.get(service, {}).get("team", "owning team"),
              "dependency": (telemetry.dependencies(service) or ["dependency"])[0], **h.params}
    status = "Mitigated" if state.verified else "Ongoing - escalated"

    lines = [
        f"# Postmortem: {service} latency and errors ({state.alert.id})", "",
        f"**Status:** {status} | **Severity:** {severity(peak)} | **Duration:** {duration} min "
        f"({hhmm(first.start)}-{hhmm(resolved_at)} UTC) | **Format:** blameless", "",
        "## Summary", "", summary, "",
        "## Impact", "",
        f"- Peak error rate on {service}: **{peak:.1f}%** (SLO {telemetry.slo(service).get('error_rate_pct', '?')}%)",
        f"- Estimated failed requests: **~{failed:,}**",
        f"- p95 latency peaked at {max(a.peak for a in state.anomalies if a.series.endswith('latency_p95_ms')):g} ms",
        "", "## Timeline (UTC)", "", "| Time | Type | Event |", "|---|---|---|",
    ]
    lines += [f"| {hhmm(e.ts)} | {e.kind} | {e.text.replace('|', '/')} |" for e in timeline]
    lines += ["", "## Root cause (most likely)", "", f"**{h.title}** - confidence {h.score:.2f}", ""]
    lines += [f"- {'+' if e.weight >= 0 else '-'} {e.text}" for e in h.evidence]
    lines += ["", "## Other hypotheses considered", ""]
    lines += [f"- {o.title} ({o.score:.2f}): " + "; ".join(e.text for e in o.evidence)
              for o in (state.hypotheses or [])[1:4]]
    lines += ["", "## What went well", "",
              f"- Alert fired {int((state.alert.fired_at - first.start).total_seconds() // 60)} min after impact began.",
              "- Every production change went through an explicit human approval with a recorded reason.",
              "", "## What was hard", ""]
    denied = state.denied()
    lines += [f"- `{r.tool}` was proposed and declined ({r.reason}). The runbook order may need revisiting."
              for r in denied] or ["- Nothing notable."]
    lines += ["", "## Action items", "", "| Action | Owner team |", "|---|---|"]
    lines += [f"| {a.format(**params)} | {o.format(**params)} |" for a, o in ACTION_ITEMS.get(h.kind, [])]
    lines += ["", "_Drafted by the incident agent from telemetry and the action log; review before publishing._", ""]
    return "\n".join(lines)
