"""Demo: a real worker process is killed mid-job; a second worker resumes it with no duplicate email.

``python demo.py``          runs the whole story (it launches the first worker as a subprocess)
``python demo.py worker``   is that subprocess: run one job, optionally crashing at a chosen step
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from .config import Settings
from .engine import CrashPlan, Engine
from .llm import MockLLM, llm_from_env
from .store import Journal
from .workflows import STEPS, make_workflows
from .world import World

WIDTH = 78
SRC = Path(__file__).resolve().parents[1]


def box(title: str, lines: list[str]) -> str:
    inner = WIDTH - 4
    top = f"+-- {title} " + "-" * max(0, WIDTH - len(title) - 6) + "+"
    body = [f"| {chunk.ljust(inner)} |" for line in lines for chunk in (textwrap.wrap(line, inner) or [""])]
    return "\n".join([top, *body, "+" + "-" * (WIDTH - 2) + "+"])


def logger(owner: str):
    def log(kind: str, message: str) -> None:
        print(f"  [{owner}] {kind:<7}| {message}", flush=True)
    return log


def build_engine(data: Path, owner: str, *, crash: CrashPlan | None = None, settings: Settings | None = None,
                 llm: MockLLM | None = None, quiet: bool = False) -> tuple[Engine, World]:
    settings = settings or Settings.from_env()
    world = World(data / "world.db")
    workflows = make_workflows(world, llm_from_env(llm or MockLLM(), settings))
    engine = Engine(Journal(data / "journal.db"), workflows, owner, lease_s=settings.lease_s,
                    log=None if quiet else logger(owner), crash=crash)
    return engine, world


def worker(args: argparse.Namespace) -> int:
    crash = None
    if args.crash_at:
        step, phase = args.crash_at.split(":")
        crash = CrashPlan(step, phase, hard=True)
    engine, _ = build_engine(Path(args.data), args.owner, crash=crash)
    asyncio.run(engine.run(args.run_id))
    return 0


def journal_view(journal: Journal, world: World, run_id: str) -> list[str]:
    done = {step: (status, attempts) for step, status, attempts in journal.steps(run_id)}
    run = journal.get_run(run_id)
    lease = (f", leased by {run.owner} for another {max(0.0, run.lease_until - time.time()):.1f}s"
             if run.status == "running" else "")
    lines = [f"run {run_id}: status={run.status}{lease}", ""]
    for step in STEPS:
        status, attempts = done.get(step, ("-", 0))
        mark = "[x]" if status == "completed" else "[ ]"
        lines.append(f"  {mark} {step:<14} {status:<10} {f'{attempts} attempt(s)' if attempts else ''}")
    lines += ["", f"outside world: emails sent = {world.emails_sent()}, CRM notes = {world.crm_notes()}"]
    return lines


def story(args: argparse.Namespace) -> int:
    data = Settings.from_env().data_dir
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    engine, world = build_engine(data, "planner", quiet=True)
    run_id = engine.start("weekly_digest", account="acme", recipient="ops@acme.example")

    print(box("ACT 1 - worker-1 starts the job and is killed", [
        f"job: weekly_digest(acme)  run_id: {run_id}",
        f"crash point: {args.crash_at} (hard kill: os._exit, no cleanup)"]), flush=True)
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    proc = subprocess.run([sys.executable, "-m", "durable", "worker", "--data", str(data), "--run-id", run_id,
                           "--owner", "worker-1", "--crash-at", args.crash_at], env=env)
    print(f"  worker-1 exited with code {proc.returncode} (killed)\n")

    print(box("ACT 2 - what survived the crash", journal_view(engine.journal, world, run_id)))
    journaled = {step for step, status, _ in engine.journal.steps(run_id) if status == "completed"}
    if world.emails_sent() and "send_email" not in journaled:
        print("  The email went out, but the journal never heard about it. A naive retry would send it again.\n")
    else:
        print("  Journaled steps are safe; everything after them will run on resume.\n")

    print(box("ACT 3 - worker-2 resumes the same run", [
        "Completed steps replay from the journal; the interrupted step runs again with the SAME idempotency key."]))
    llm = MockLLM()
    resumer, _ = build_engine(data, "worker-2", llm=llm)
    result = asyncio.run(resumer.run_when_free(run_id))

    print()
    print(box("ACT 4 - proof", journal_view(resumer.journal, world, run_id) + [
        "",
        f"LLM calls made by worker-2: {llm.calls} " + ("(all model outputs replayed from journal)"
                                                        if llm.calls == 0 else "(only for steps that never finished)"),
        f"result: {result['summary']}",
        "exactly-once effects: " + ("YES" if world.emails_sent() == 1 and world.crm_notes() == 1 else "NO"),
    ]))
    return 0 if world.emails_sent() == 1 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable agent workflows: checkpoints, retries, resume")
    parser.add_argument("--crash-at", default="send_email:after_effect",
                        help="step:phase where worker-1 dies (phase: before | after_effect)")
    sub = parser.add_subparsers(dest="command")
    w = sub.add_parser("worker", help="run one job (used by the demo as a subprocess)")
    w.add_argument("--data", required=True)
    w.add_argument("--run-id", required=True)
    w.add_argument("--owner", default="worker")
    w.add_argument("--crash-at")
    args = parser.parse_args(argv)
    return worker(args) if args.command == "worker" else story(args)
