"""Durability guarantees: resume after any crash, exactly-once effects, no repeated LLM calls, leases."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from durable.engine import CrashPlan, Engine, SimulatedCrash, StepFailed
from durable.llm import MockLLM
from durable.store import Journal, LeaseHeld
from durable.workflows import STEPS, make_workflows
from durable.world import World

SRC = Path(__file__).resolve().parents[1] / "src"
INPUT = {"account": "acme", "recipient": "ops@acme.example"}


def make(data: Path, owner: str, *, crash=None, llm=None, ticket_failures=0, lease_s=0.01):
    world = World(data / "world.db", ticket_failures=ticket_failures)
    llm = llm or MockLLM()
    engine = Engine(Journal(data / "journal.db"), make_workflows(world, llm), owner, lease_s=lease_s, crash=crash)
    return engine, world, llm


def resume(data: Path, **kwargs):
    engine, world, llm = make(data, "worker-2", **kwargs)
    return asyncio.run(engine.run_when_free(run_id(data), poll_s=0.01)), engine, world, llm


def run_id(data: Path) -> str:
    return Journal(data / "journal.db").conn.execute("SELECT run_id FROM runs").fetchone()[0]


def test_clean_run_completes_with_one_of_each_effect(tmp_path):
    engine, world, llm = make(tmp_path, "w1")
    result = asyncio.run(engine.run(engine.start("weekly_digest", **INPUT)))
    assert result["summary"].startswith("3 tickets this week: 2 resolved, 1 open")
    assert world.emails_sent() == 1 and world.crm_notes() == 1 and llm.calls == 2


@pytest.mark.parametrize("phase", ["before", "after_effect"])
@pytest.mark.parametrize("step", STEPS)
def test_crash_anywhere_then_resume_gives_exactly_once_effects(tmp_path, step, phase):
    engine, _, _ = make(tmp_path, "worker-1", crash=CrashPlan(step, phase))
    with pytest.raises(SimulatedCrash):
        asyncio.run(engine.run(engine.start("weekly_digest", **INPUT)))

    result, resumer, world, _ = resume(tmp_path)
    assert world.emails_sent() == 1 and world.crm_notes() == 1
    assert [s for s, status, _ in resumer.journal.steps(run_id(tmp_path)) if status == "completed"] == STEPS
    assert result["account"] == "acme" and result["message_id"].startswith("msg-")


def test_resume_replays_llm_results_instead_of_asking_again(tmp_path):
    engine, _, first_llm = make(tmp_path, "worker-1", crash=CrashPlan("send_email", "after_effect"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(engine.run(engine.start("weekly_digest", **INPUT)))
    _, _, _, llm = resume(tmp_path)
    assert first_llm.calls == 2 and llm.calls == 0


def test_interrupted_llm_step_is_the_only_one_redone(tmp_path):
    engine, _, _ = make(tmp_path, "worker-1", crash=CrashPlan("draft_email", "before"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(engine.run(engine.start("weekly_digest", **INPUT)))
    _, _, _, llm = resume(tmp_path)
    assert llm.calls == 1


def test_transient_errors_are_retried_and_attempts_recorded(tmp_path):
    engine, world, _ = make(tmp_path, "w1", ticket_failures=2)
    rid = engine.start("weekly_digest", **INPUT)
    asyncio.run(engine.run(rid))
    assert engine.journal.steps(rid)[0] == ("fetch_tickets", "completed", 3)
    assert world.ticket_calls == 3


def test_retries_are_bounded_and_failed_runs_stay_failed(tmp_path):
    engine, world, _ = make(tmp_path, "w1", ticket_failures=99)
    rid = engine.start("weekly_digest", **INPUT)
    with pytest.raises(StepFailed, match="after 4 attempts"):
        asyncio.run(engine.run(rid))
    assert engine.journal.get_run(rid).status == "failed"
    calls = world.ticket_calls
    with pytest.raises(StepFailed):
        asyncio.run(engine.run(rid))
    assert world.ticket_calls == calls and world.emails_sent() == 0


def test_permanent_errors_are_not_retried(tmp_path):
    engine, world, _ = make(tmp_path, "w1")
    rid = engine.start("weekly_digest", account="nobody", recipient="x@example.com")
    with pytest.raises(StepFailed, match="PermanentError"):
        asyncio.run(engine.run(rid))
    assert world.ticket_calls == 1


def test_completed_runs_are_not_executed_twice(tmp_path):
    engine, world, llm = make(tmp_path, "w1")
    rid = engine.start("weekly_digest", **INPUT)
    first = asyncio.run(engine.run(rid))
    assert asyncio.run(engine.run(rid)) == first
    assert llm.calls == 2 and world.emails_sent() == 1


def test_lease_blocks_a_second_worker_until_it_expires(tmp_path):
    journal = Journal(tmp_path / "journal.db")
    rid = journal.create_run("weekly_digest", INPUT)
    journal.claim(rid, "worker-1", lease_s=10, now=1000)
    with pytest.raises(LeaseHeld, match="worker-1"):
        journal.claim(rid, "worker-2", lease_s=10, now=1005)
    journal.claim(rid, "worker-1", lease_s=10, now=1005)  # the owner may renew
    journal.claim(rid, "worker-2", lease_s=10, now=1016)  # expired -> taken over
    assert journal.get_run(rid).owner == "worker-2"


def test_idempotency_key_makes_email_sends_safe_to_repeat(tmp_path):
    world = World(tmp_path / "world.db")
    first = asyncio.run(world.send_email("a@b.c", "s", "b", idempotency_key="run-1/send_email"))
    again = asyncio.run(world.send_email("a@b.c", "s", "b", idempotency_key="run-1/send_email"))
    assert again == {"message_id": first["message_id"], "duplicate": True}
    assert world.emails_sent() == 1


def test_step_results_must_be_json_and_names_unique(tmp_path):
    journal = Journal(tmp_path / "journal.db")

    async def returns_object(ctx):
        async def make_object(_):
            return object()
        return await ctx.step("bad", make_object)

    async def reuses_name(ctx):
        async def ok(_):
            return 1
        await ctx.step("same", ok)
        return await ctx.step("same", ok)

    engine = Engine(journal, {"bad": returns_object, "dup": reuses_name}, "w1")
    with pytest.raises(TypeError):
        asyncio.run(engine.run(engine.start("bad")))
    with pytest.raises(ValueError, match="used twice"):
        asyncio.run(engine.run(engine.start("dup")))


def test_survives_a_real_process_kill(tmp_path):
    engine, _, _ = make(tmp_path, "planner")
    rid = engine.start("weekly_digest", **INPUT)
    proc = subprocess.run(
        [sys.executable, "-m", "durable", "worker", "--data", str(tmp_path), "--run-id", rid,
         "--owner", "worker-1", "--crash-at", "send_email:after_effect"],
        env={**os.environ, "PYTHONPATH": str(SRC)}, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 137, proc.stderr
    assert World(tmp_path / "world.db").emails_sent() == 1  # the effect happened before the kill

    result, _, world, _ = resume(tmp_path)
    assert world.emails_sent() == 1 and world.crm_notes() == 1
    assert result["message_id"].startswith("msg-")
