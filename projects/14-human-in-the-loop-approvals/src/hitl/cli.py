"""Command line: a scripted end-to-end story, plus real subcommands for running it by hand.

    python demo.py                                   # the full story (scripted approvers)
    python demo.py start "Order A-1042 ..." --by sam # start a run; it pauses at the first risky step
    python demo.py pending                           # show what is waiting
    python demo.py approve RUN_ID --by alice --comment "checked the ledger"
    python demo.py reject  RUN_ID --by bob --comment "open invoice"
    python demo.py resume  RUN_ID
    python demo.py audit                             # print and verify the hash-chained log
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .actions import Backoffice
from .agent import ApprovalAgent, Executor
from .approvals import ApprovalError
from .audit import AuditLog
from .config import Settings, load_settings
from .llm import PlannerMockLLM, llm_from_env
from .render import approval_card, audit_table, box, print_event
from .risk import RiskPolicy
from .store import RunState, RunStore

TASK = ("Order A-1042 was charged twice. Refund the duplicate charge, tell the customer, "
        "and close their duplicate account.")


def risk_policy(settings: Settings) -> RiskPolicy:
    return RiskPolicy(company_domains=settings.company_domains, large_amount=settings.large_amount,
                      very_large_amount=settings.very_large_amount)


def build_agent(state_dir: Path, verbose: bool = True) -> ApprovalAgent:
    """Everything is rebuilt from disk, exactly like a fresh process would."""
    settings = load_settings()
    executor = Executor(Backoffice(state_dir / "world.json"), risk_policy(settings))
    return ApprovalAgent(llm_from_env(PlannerMockLLM()), executor, RunStore(state_dir / "runs"),
                         AuditLog(state_dir / "audit.jsonl"), emit=print_event if verbose else _silent,
                         max_steps=settings.max_steps)


def _silent(kind: str, title: str, lines: list[str]) -> None:
    return None


def _show_pause(state: RunState) -> None:
    if state.status == "waiting_approval" and state.pending:
        print(approval_card(state.pending))


def story(state_dir: Path) -> None:
    shutil.rmtree(state_dir, ignore_errors=True)

    print(box("1. sam (support lead) starts the run", [f"task: {TASK}"]))
    state = build_agent(state_dir).start(TASK, requested_by="sam")
    _show_pause(state)
    print(f"\n  (process exits; the run waits on disk in {state_dir / 'runs' / (state.id + '.json')})\n")

    run_id = state.id
    print(box("2. a new process: the humans decide", []))
    agent = build_agent(state_dir)
    try:
        agent.decide(run_id, "sam", True, "looks fine to me")
    except ApprovalError as exc:
        print(f"[refused] sam -> {exc}")
    try:
        agent.decide(run_id, "alice", True, "")
    except ApprovalError as exc:
        print(f"[refused] alice (no reason) -> {exc}")
    agent.decide(run_id, "alice", True, "Ledger shows two captures for A-1042")
    print("[human+] alice approved req with a reason\n")
    state = agent.resume(run_id)
    _show_pause(state)

    print(box("3. alice approves the customer email", []))
    agent.decide(run_id, "alice", True, "wording ok")
    state = agent.resume(run_id)
    _show_pause(state)

    print(box("4. CRITICAL needs two people: alice yes, bob no", []))
    agent.decide(run_id, "alice", True, "duplicate account confirmed")
    print(f"[human+] alice approved   -> request is still {agent.store.load(run_id).pending.status} (1/2)")
    agent.decide(run_id, "bob", False, "C-78 still has an open invoice; do not purge")
    state = agent.resume(run_id)

    print()
    audit = AuditLog(state_dir / "audit.jsonl")
    print(box("5. audit log (hash-chained)", []))
    print(audit_table(audit.entries()))
    ok, message = audit.verify()
    print(f"\nverify(): {message}")
    _tamper_demo(audit)


def _tamper_demo(audit: AuditLog) -> None:
    lines = audit.path.read_text(encoding="utf-8").splitlines()
    forged = [line.replace('"approver": "bob"', '"approver": "alice"') for line in lines]
    copy = audit.path.with_name("audit.tampered.jsonl")
    copy.write_text("\n".join(forged) + "\n", encoding="utf-8")
    ok, message = AuditLog(copy).verify()
    print(f"verify() after someone edits bob's rejection: {message}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Human-in-the-loop approvals")
    parser.add_argument("--state", type=Path, default=load_settings().state_dir,
                        help="where runs and the audit log live (env: HITL_STATE_DIR)")
    sub = parser.add_subparsers(dest="cmd")
    start = sub.add_parser("start")
    start.add_argument("task", nargs="?", default=TASK)
    start.add_argument("--by", default="sam")
    sub.add_parser("pending")
    for name in ("approve", "reject"):
        cmd = sub.add_parser(name)
        cmd.add_argument("run_id")
        cmd.add_argument("--by", required=True)
        cmd.add_argument("--comment", default="")
    sub.add_parser("resume").add_argument("run_id")
    sub.add_parser("audit")
    args = parser.parse_args(argv)

    if args.cmd is None:
        story(args.state)
        return
    agent = build_agent(args.state)
    if args.cmd == "start":
        _show_pause(agent.start(args.task, args.by))
    elif args.cmd == "pending":
        waiting = [s for s in agent.store.all() if s.status == "waiting_approval" and s.pending]
        for s in waiting:
            print(approval_card(s.pending))
        print(f"{len(waiting)} run(s) waiting")
    elif args.cmd in ("approve", "reject"):
        request = agent.decide(args.run_id, args.by, args.cmd == "approve", args.comment)
        print(f"{request.id} is now {request.status}")
    elif args.cmd == "resume":
        _show_pause(agent.resume(args.run_id))
    elif args.cmd == "audit":
        audit = AuditLog(args.state / "audit.jsonl")
        print(audit_table(audit.entries()))
        print(audit.verify()[1])
