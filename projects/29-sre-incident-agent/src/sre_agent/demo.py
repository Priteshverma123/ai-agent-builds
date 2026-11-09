"""Demo: the agent triages ALERT-5521, asks a human before touching production, writes the postmortem.

Run:  python demo.py                 (scripted on-call answers)
      python demo.py --interactive   (you are the on-call: answer y/n)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from sre_agent.adapters.approval import ConsoleApprover, ScriptedApprover
from sre_agent.adapters.infra import MockInfra
from sre_agent.adapters.llm import default_llm
from sre_agent.adapters.telemetry import FileTelemetry, load_alert
from sre_agent.config import PROJECT_ROOT, Settings
from sre_agent.domain.models import Decision, hhmm
from sre_agent.services.agent import IncidentAgent
from sre_agent.services.postmortem import lint_blameless, render
from sre_agent.services.timeline import build_timeline

WIDTH = 78
ONCALL = "on-call (alex)"
SCRIPT = {
    "freeze_deploys": Decision(True, ONCALL, "cheap and reversible"),
    "restart_service": Decision(False, ONCALL, "a restart won't undo a config change; roll back instead"),
    "rollback_deploy": Decision(True, ONCALL, "regression started 2 min after the deploy"),
}


def box(title: str) -> None:
    print("\n+" + "-" * (WIDTH - 2) + "+\n| " + title.ljust(WIDTH - 4) + " |\n+" + "-" * (WIDTH - 2) + "+")


def wrap(text: str, indent: int) -> str:
    return textwrap.fill(text, WIDTH, initial_indent=" " * indent, subsequent_indent=" " * indent)


def on_event(kind: str, d: dict) -> None:
    if kind == "think":
        print(f"\n  [{d['step']:>2}] {hhmm(d['ts'])}  THINK")
        print(wrap(d["thought"], 14))
    elif kind == "act":
        args = ", ".join(f"{k}={v}" for k, v in d["args"].items())
        gate = "  -> needs human approval" if d["approval"] else ""
        print(f"              ACT     {d['tool']}({args})  risk={d['risk']}{gate}")
    elif kind == "observe":
        r = d["record"]
        if r.status == "denied":
            print(f"              DENIED  by {r.approver}: {r.reason}")
            return
        if r.approver:
            print(f"              OK      approved by {r.approver}: {r.reason}")
        print(wrap(f"OBSERVE {r.summary}", 14))
    elif kind == "plan":
        print(f"              PLAN    runbook '{d['title']}': " + " > ".join(d["steps"]))
    elif kind == "finish":
        print(f"              FINISH  status={d['status']}")


def display_path(path: Path) -> Path:
    """Show paths inside the project relative to it (out/postmortem.md), others in full."""
    return path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path


def main(interactive: bool = False, settings: Settings | None = None) -> None:
    settings = settings or Settings.from_env()
    examples = settings.examples_dir
    telemetry, alert = FileTelemetry(examples / "incident"), load_alert(examples / "alert.json")
    approver = ConsoleApprover(ONCALL) if interactive else ScriptedApprover(SCRIPT)
    llm = default_llm(settings)
    agent = IncidentAgent(llm, telemetry, MockInfra(), approver, examples / "runbooks.json", on_event,
                          max_steps=settings.max_steps)

    box(f"exe_404.ai  |  29 . SRE Incident Agent   {alert.id} @ {hhmm(alert.fired_at)} UTC")
    print(f"  alert: {alert.rule}")
    state, clock = agent.run(alert)

    box("Hypotheses (evidence-scored)")
    for h in (state.hypotheses or [])[:4]:
        print(f"  {h.score:>4.2f}  {h.title}")
    if state.top_hypothesis:
        for e in state.top_hypothesis.evidence:
            print(f"          {'+' if e.weight >= 0 else '-'}{abs(e.weight):.2f}  {e.text}")

    timeline = build_timeline(state)
    box("Incident timeline (UTC)")
    for e in timeline:
        print(f"  {hhmm(e.ts)}  {e.kind:<10} {e.text[:58]}")

    md = render(state, timeline, telemetry, llm.summarize(state), clock.now())
    out = settings.out_dir / "postmortem.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    issues = lint_blameless(md)
    box("Blameless postmortem draft")
    for line in md.splitlines()[:6]:
        print("  " + line)
    print(f"  ... ({len(md.splitlines())} lines) written to {display_path(out)}")
    print(f"  blameless lint: {'PASS' if not issues else 'FAIL'} ({len(issues)} issues)")
    print()
