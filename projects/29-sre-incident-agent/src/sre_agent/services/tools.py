"""Runbook steps as tools, each with a risk level, and a registry that enforces approval.

The safety rule lives HERE, not in the prompt: any tool marked `mutating` is sent to a human approver
before it runs, whatever the LLM says. A model can be talked into anything; a registry can't.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from sre_agent.adapters.approval import Approver
from sre_agent.adapters.clock import SimClock
from sre_agent.adapters.infra import MockInfra
from sre_agent.adapters.telemetry import FileTelemetry
from sre_agent.domain.models import Action, ActionRecord, ApprovalRequest, Risk, parse_ts
from sre_agent.domain.state import AgentState
from sre_agent.services import anomaly, hypotheses, logs


@dataclass(frozen=True)
class ToolResult:
    summary: str
    data: Any = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: tuple[str, ...]
    risk: Risk
    mutating: bool
    run: Callable[..., ToolResult]
    preview: Callable[..., str] | None = None


class ToolRegistry:
    def __init__(self, tools: list[Tool], approver: Approver, clock: SimClock) -> None:
        self.tools = {t.name: t for t in tools}
        self.approver = approver
        self.clock = clock

    def catalog(self) -> list[dict[str, Any]]:
        """What an LLM is told about the tools (the same shape you'd send as tool schemas)."""
        return [{"name": t.name, "description": t.description, "params": list(t.params),
                 "risk": t.risk.value, "needs_approval": t.mutating} for t in self.tools.values()]

    def execute(self, action: Action) -> tuple[ActionRecord, ToolResult | None]:
        tool = self.tools.get(action.tool)
        if tool is None:
            return self._record(action, Risk.NONE, "failed", f"unknown tool '{action.tool}'"), None
        missing = [p for p in tool.params if p not in action.args]
        if missing:
            return self._record(action, tool.risk, "failed", f"missing args: {', '.join(missing)}"), None
        approver = reason = ""
        if tool.mutating:
            preview = tool.preview(**action.args) if tool.preview else f"{tool.name}({action.args})"
            decision = self.approver.decide(ApprovalRequest(tool.name, action.args, tool.risk, preview, action.thought))
            self.clock.advance(2)  # humans take a moment
            approver, reason = decision.approver, decision.reason
            if not decision.approved:
                return self._record(action, tool.risk, "denied", "not executed", approver, reason), None
        result = tool.run(**action.args)
        self.clock.advance(1)
        return self._record(action, tool.risk, "executed", result.summary, approver, reason), result

    def _record(self, action: Action, risk: Risk, status: str, summary: str,
                approver: str = "", reason: str = "") -> ActionRecord:
        return ActionRecord(self.clock.now(), action.tool, dict(action.args), risk, status, summary, approver, reason)


def build_toolbox(telemetry: FileTelemetry, infra: MockInfra, state: AgentState,
                  approver: Approver, clock: SimClock) -> ToolRegistry:
    """Wire every tool to its data source. Read-only tools see telemetry up to the alert time only."""
    until = state.alert.fired_at + timedelta(minutes=3)

    def detect_anomalies() -> ToolResult:
        found = anomaly.detect_all(telemetry.all_series())
        lines = [f"{a.series} since {a.start:%H:%M} ({a.baseline:g} -> {a.peak:g}, z={a.z_score})" for a in found]
        return ToolResult(f"{len(found)} anomalies: " + "; ".join(lines) if found else "no anomalies", found)

    def search_logs(since: str, min_level: str = "WARN") -> ToolResult:
        sigs = logs.signatures(telemetry.logs(since=parse_ts(since), until=until, min_level=min_level))
        lines = [f"{s.count}x {s.service}: {s.template}" for s in sigs]
        return ToolResult(f"{len(sigs)} signatures: " + " | ".join(lines), sigs)

    def list_deploys(since: str) -> ToolResult:
        found = telemetry.deploys(since=parse_ts(since), until=until)
        lines = [f"{d.ts:%H:%M} {d.service} {d.previous_version}->{d.version} {d.pr}" for d in found]
        return ToolResult(f"{len(found)} deploys: " + "; ".join(lines), found)

    def rank_hypotheses() -> ToolResult:
        ranked = hypotheses.rank(telemetry, state.anomalies or [], state.signatures or [], state.deploys or [])
        return ToolResult(" > ".join(f"{h.title} ({h.score:.2f})" for h in ranked[:3]), ranked)

    def verify_recovery(service: str) -> ToolResult:
        health, slo = infra.health(service), telemetry.slo(service)
        healthy = all(health[k] <= v for k, v in slo.items() if k in health)
        status = "within SLO" if healthy else "STILL BREACHING SLO"
        return ToolResult(f"{service} p95={health['latency_p95_ms']}ms errors={health['error_rate_pct']}% "
                          f"-> {status}", {"healthy": healthy, **health})

    def page_oncall(team: str, summary: str) -> ToolResult:
        return ToolResult(f"paged team '{team}': {summary}", {"team": team})

    def wrap(fn: Callable[..., str]) -> Callable[..., ToolResult]:
        return lambda **kw: ToolResult(fn(**kw))

    return ToolRegistry([
        Tool("detect_anomalies", "Robust z-score scan of every metric", (), Risk.NONE, False, detect_anomalies),
        Tool("search_logs", "Group WARN/ERROR logs into signatures", ("since",), Risk.NONE, False, search_logs),
        Tool("list_deploys", "Deploys in a time window", ("since",), Risk.NONE, False, list_deploys),
        Tool("rank_hypotheses", "Score candidate causes against evidence", (), Risk.NONE, False, rank_hypotheses),
        Tool("verify_recovery", "Compare live health with the SLO", ("service",), Risk.NONE, False, verify_recovery),
        Tool("page_oncall", "Escalate to the owning team", ("team", "summary"), Risk.LOW, False, page_oncall),
        Tool("freeze_deploys", "Block new deploys to a service", ("service",), Risk.LOW, True,
             wrap(lambda service: infra.freeze_deploys(service)),
             lambda service: f"block the CD pipeline for {service} (reversible: unfreeze)"),
        Tool("restart_service", "Rolling restart of all pods", ("service",), Risk.MEDIUM, True,
             wrap(lambda service: infra.restart(service)),
             lambda service: f"rolling restart of {infra.replicas.get(service, 1)} {service} pods"),
        Tool("rollback_deploy", "Roll a service back to a previous version", ("service", "to_version"), Risk.HIGH,
             True, wrap(lambda service, to_version: infra.rollback(service, to_version)),
             lambda service, to_version: f"{service} {infra.versions[service]} -> {to_version} on "
                                         f"{infra.replicas.get(service, 1)} pods (rolling, ~4 min)"),
        Tool("scale_db_connections", "Change a database's max_connections", ("service", "max_connections"),
             Risk.HIGH, True, wrap(lambda service, max_connections: infra.set_max_connections(service, max_connections)),
             lambda service, max_connections: f"{service} max_connections "
                                               f"{infra.max_connections.get(service)} -> {max_connections} (restart)"),
        Tool("scale_out", "Change replica count", ("service", "replicas"), Risk.MEDIUM, True,
             wrap(lambda service, replicas: infra.scale(service, replicas)),
             lambda service, replicas: f"{service} {infra.replicas.get(service)} -> {replicas} replicas"),
    ], approver, clock)
