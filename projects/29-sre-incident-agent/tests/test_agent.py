"""The agent loop, the approval gate, the timeline and the postmortem."""
from __future__ import annotations

from conftest import make_agent
from sre_agent.adapters.approval import ConsoleApprover, DenyAll
from sre_agent.adapters.clock import SimClock
from sre_agent.adapters.infra import BAD_VERSION, MockInfra
from sre_agent.domain.models import Action, ApprovalRequest, Risk
from sre_agent.domain.state import AgentState
from sre_agent.services.postmortem import lint_blameless, render
from sre_agent.services.timeline import build_timeline
from sre_agent.services.tools import build_toolbox


def test_happy_path_mitigates_with_rollback(telemetry, alert) -> None:
    agent, approver, infra = make_agent(telemetry, {"freeze_deploys": True, "restart_service": False,
                                                    "rollback_deploy": True})
    state, _ = agent.run(alert)
    assert state.status == "mitigated" and state.verified is True
    assert infra.versions["checkout-api"] == "v2.13.2"
    assert [r.tool for r in approver.seen] == ["freeze_deploys", "restart_service", "rollback_deploy"]
    assert infra.restarts == {}  # denied step never ran


def test_every_mutating_step_asks_first(telemetry, alert) -> None:
    agent, approver, _ = make_agent(telemetry, {"freeze_deploys": True, "restart_service": True,
                                                "rollback_deploy": True})
    state, _ = agent.run(alert)
    executed_mutations = [r for r in state.records if r.risk in (Risk.MEDIUM, Risk.HIGH) or r.tool == "freeze_deploys"]
    assert executed_mutations and all(r.approver == "tester" for r in executed_mutations)
    assert {r.risk for r in approver.seen} == {Risk.LOW, Risk.MEDIUM, Risk.HIGH}
    assert "v2.14.0 -> v2.13.2" in approver.seen[-1].preview


def test_denied_rollback_escalates_instead_of_pretending(telemetry, alert) -> None:
    agent, _, infra = make_agent(telemetry, {"freeze_deploys": True, "restart_service": True,
                                             "rollback_deploy": False})
    state, _ = agent.run(alert)
    assert infra.versions["checkout-api"] == BAD_VERSION
    assert state.verified is False and state.paged and state.status == "escalated"


def test_registry_blocks_mutations_without_approver(telemetry, alert) -> None:
    infra = MockInfra()
    registry = build_toolbox(telemetry, infra, AgentState(alert), DenyAll(), SimClock(alert.fired_at))
    record, result = registry.execute(Action("the model insists", "rollback_deploy",
                                             {"service": "checkout-api", "to_version": "v1"}))
    assert record.status == "denied" and result is None and infra.versions["checkout-api"] == BAD_VERSION


def test_registry_rejects_unknown_tools_and_missing_args(telemetry, alert) -> None:
    registry = build_toolbox(telemetry, MockInfra(), AgentState(alert), DenyAll(), SimClock(alert.fired_at))
    assert registry.execute(Action("", "rm_rf", {}))[0].status == "failed"
    assert "missing args" in registry.execute(Action("", "rollback_deploy", {"service": "x"}))[0].summary


def test_restart_alone_does_not_fix_the_bad_config() -> None:
    infra = MockInfra()
    infra.restart("checkout-api")
    infra.scale("checkout-api", 12)
    assert infra.health("checkout-api")["error_rate_pct"] > 11.4  # more pods = more pool pressure


def test_console_approver_parses_answers() -> None:
    req = ApprovalRequest("rollback_deploy", {}, Risk.HIGH, "", "")
    assert ConsoleApprover("me", ask=lambda _: "yes looks right").decide(req).reason == "looks right"
    assert ConsoleApprover("me", ask=lambda _: "n").decide(req).approved is False
    assert ConsoleApprover("me", ask=lambda _: "yolo").decide(req).approved is False


def test_trace_events_follow_think_act_observe(telemetry, alert) -> None:
    events: list = []
    agent, _, _ = make_agent(telemetry, {"freeze_deploys": True, "rollback_deploy": True}, events=events)
    agent.run(alert)
    kinds = [k for k, _ in events]
    assert kinds[:3] == ["think", "act", "observe"] and "plan" in kinds and kinds[-1] == "finish"


def test_timeline_is_ordered_and_records_decisions(telemetry, alert) -> None:
    agent, _, _ = make_agent(telemetry, {"freeze_deploys": True, "restart_service": False, "rollback_deploy": True})
    state, _ = agent.run(alert)
    tl = build_timeline(state)
    assert [e.ts for e in tl] == sorted(e.ts for e in tl)
    assert tl[-1].kind == "resolution"
    assert any(e.kind == "decision" and "restart_service" in e.text for e in tl)


def test_postmortem_has_sections_and_is_blameless(telemetry, alert) -> None:
    agent, _, _ = make_agent(telemetry, {"freeze_deploys": True, "restart_service": False, "rollback_deploy": True})
    state, clock = agent.run(alert)
    md = render(state, build_timeline(state), telemetry, "summary", clock.now())
    for heading in ("## Summary", "## Impact", "## Timeline (UTC)", "## Root cause", "## Action items"):
        assert heading in md
    assert "SEV2" in md and "v2.14.0" in md
    assert lint_blameless(md) == []


def test_blameless_lint_flags_blame() -> None:
    issues = lint_blameless("Summary\nThe outage was Sam's fault: careless config.\nhuman error again")
    assert len(issues) == 3 and issues[0].startswith("line 2")
