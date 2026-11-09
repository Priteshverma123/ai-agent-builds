"""Merge changes, symptoms, detection and agent actions into one ordered timeline."""
from __future__ import annotations

from sre_agent.domain.models import TimelineEntry
from sre_agent.domain.state import AgentState


def build_timeline(state: AgentState) -> list[TimelineEntry]:
    out: list[TimelineEntry] = []
    for d in state.deploys or []:
        out.append(TimelineEntry(d.ts, "change", f"{d.service} {d.version} deployed ({d.pr}): {d.change}"))
    for a in state.anomalies or []:
        out.append(TimelineEntry(a.start, "symptom", f"{a.series} leaves baseline ({a.baseline:g} -> peak {a.peak:g})"))
    for s in (state.signatures or [])[:2]:
        out.append(TimelineEntry(s.first_seen, "symptom", f"first {s.service} error: \"{s.template[:60]}\""))
    out.append(TimelineEntry(state.alert.fired_at, "detection", f"{state.alert.id} fired: {state.alert.rule}"))
    for r in state.records:
        if r.risk.value == "none" and r.tool != "verify_recovery":
            continue  # read-only investigation steps are in the agent trace, not the incident timeline
        if r.status == "denied":
            text = f"{r.tool} proposed by agent, declined by {r.approver}: {r.reason}"
            out.append(TimelineEntry(r.ts, "decision", text))
            continue
        who = f" (approved by {r.approver})" if r.approver else ""
        kind = "resolution" if r.tool == "verify_recovery" and "within SLO" in r.summary else "action"
        out.append(TimelineEntry(r.ts, kind, f"{r.summary}{who}"))
    return sorted(out, key=lambda e: e.ts)
