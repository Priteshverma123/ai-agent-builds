"""Generate candidate causes and score each one against explicit evidence.

Every point added or removed is an `Evidence` line with a reason. A score you can't explain is a score an
on-call engineer won't trust at 3 a.m.
"""
from __future__ import annotations

from sre_agent.adapters.telemetry import FileTelemetry
from sre_agent.domain.models import Anomaly, Deploy, ErrorSignature, Evidence, Hypothesis
from sre_agent.services.logs import keywords


def _minutes(a, b) -> float:
    return (b - a).total_seconds() / 60


def deploy_hypothesis(d: Deploy, first: Anomaly, anomalous: set[str], sigs: list[ErrorSignature],
                      dep_anomalies: list[Anomaly]) -> Hypothesis:
    h = Hypothesis("bad_deploy", f"{d.service} {d.version} deploy ({d.pr}) caused the regression",
                   {"service": d.service, "version": d.version, "previous_version": d.previous_version,
                    "deploy_id": d.id, "change": d.change})
    h.evidence.append(Evidence("a change is the most common trigger of incidents", 0.05))
    gap = _minutes(d.ts, first.start)
    if 0 <= gap <= 15:
        h.evidence.append(Evidence(f"deployed {gap:.0f} min before the first anomaly", 0.35))
    elif 0 <= gap <= 60:
        h.evidence.append(Evidence(f"deployed {gap:.0f} min before the first anomaly (weak timing)", 0.10))
    else:
        h.evidence.append(Evidence("deployed after the anomaly started", -0.30))
    if d.service in anomalous:
        h.evidence.append(Evidence(f"{d.service} is itself anomalous", 0.20))
    else:
        h.evidence.append(Evidence(f"{d.service} shows no anomaly of its own", -0.05))
    error_words = set().union(*(keywords(s.template) for s in sigs)) if sigs else set()
    overlap = sorted(keywords(d.change) & error_words)
    if overlap:
        h.evidence.append(Evidence(f"errors mention {', '.join(overlap)}, which the change touched", 0.25))
    if "pool" in d.change.lower() and any("connections" in a.series for a in dep_anomalies):
        h.evidence.append(Evidence("DB connection count jumped right after a pool-size change", 0.10))
    return h


def traffic_hypothesis(service: str, telemetry: FileTelemetry, first: Anomaly) -> Hypothesis | None:
    name = f"{service}.requests_per_s"
    try:
        s = telemetry.series(name)
    except KeyError:
        return None
    h = Hypothesis("traffic_surge", f"traffic surge on {service}", {"service": service})
    idx = int(_minutes(s.start, first.start))
    before = sum(s.values[max(0, idx - 10):idx]) / max(1, min(10, idx))
    after = sum(s.values[idx:]) / max(1, len(s.values) - idx)
    change = (after - before) / before * 100
    if change > 50:
        h.evidence.append(Evidence(f"{name} up {change:.0f}% ({before:.0f} -> {after:.0f})", 0.6))
    else:
        h.evidence.append(Evidence(f"{name} flat ({before:.0f} -> {after:.0f}, {change:+.0f}%)", 0.05))
    return h


def dependency_hypotheses(service: str, telemetry: FileTelemetry, dep_anomalies: list[Anomaly],
                          sigs: list[ErrorSignature], has_recent_deploy: bool) -> list[Hypothesis]:
    out = []
    for dep in telemetry.dependencies(service):
        mine = [a for a in dep_anomalies if a.service == dep]
        h = Hypothesis("dependency_saturation", f"{dep} saturated and slowing {service}",
                       {"service": service, "dependency": dep})
        if not mine:
            h.evidence.append(Evidence(f"{dep} metrics are normal", 0.02))
            out.append(h)
            continue
        a = mine[0]
        h.evidence.append(Evidence(f"{a.series} {a.baseline:g} -> {a.peak:g} ({a.change_pct:+.0f}%)", 0.40))
        if any(dep.split("-")[0] in s.template for s in sigs):
            h.evidence.append(Evidence(f"{service} errors name {dep.split('-')[0]}", 0.15))
        cpu = f"{dep}.cpu_pct"
        if cpu in {s.name for s in telemetry.all_series()} and not any(x.series == cpu for x in dep_anomalies):
            h.evidence.append(Evidence(f"{cpu} normal: {dep} is healthy but flooded", -0.10))
        if has_recent_deploy:
            h.evidence.append(Evidence("saturation began with a client deploy: likely a symptom", -0.15))
        out.append(h)
    return out


def rank(telemetry: FileTelemetry, anomalies: list[Anomaly], sigs: list[ErrorSignature],
         deploys: list[Deploy]) -> list[Hypothesis]:
    """All candidate causes for the incident, best first."""
    if not anomalies:
        return []
    first = min(anomalies, key=lambda a: a.start)
    service = first.service
    anomalous = {a.service for a in anomalies}
    dep_anomalies = [a for a in anomalies if a.service in telemetry.dependencies(service)]
    hyps = [deploy_hypothesis(d, first, anomalous, sigs, dep_anomalies) for d in deploys]
    recent = any(0 <= _minutes(d.ts, first.start) <= 15 for d in deploys)
    hyps += dependency_hypotheses(service, telemetry, dep_anomalies, sigs, recent)
    if (t := traffic_hypothesis(service, telemetry, first)) is not None:
        hyps.append(t)
    return sorted(hyps, key=lambda h: -h.score)
