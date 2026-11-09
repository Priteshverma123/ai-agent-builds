import json

import pytest

from hitl.actions import TOOL_SPECS, Action, Backoffice
from hitl.agent import ApprovalAgent, Executor
from hitl.approvals import ApprovalError
from hitl.audit import AuditLog
from hitl.llm import PlannerMockLLM
from hitl.risk import Level, RiskPolicy
from hitl.store import RunStore

TASK = "Order A-1042 was charged twice. Refund the duplicate charge, tell the customer, and close their duplicate account."


def make_agent(tmp_path, executor_cls=Executor):
    executor = executor_cls(Backoffice(tmp_path / "world.json"), RiskPolicy())
    return ApprovalAgent(PlannerMockLLM(), executor, RunStore(tmp_path / "runs"), AuditLog(tmp_path / "audit.jsonl"))


def world(tmp_path):
    return json.loads((tmp_path / "world.json").read_text()) if (tmp_path / "world.json").exists() else None


def executed(tmp_path, tool):
    entries = AuditLog(tmp_path / "audit.jsonl").entries()
    return [e for e in entries if e["event"] == "executed" and e["data"]["action"]["tool"] == tool]


# ---------------------------------------------------------------- risk scoring

@pytest.mark.parametrize("action, level", [
    (Action("lookup_order", {"order_id": "A-1"}), Level.LOW),
    (Action("issue_refund", {"order_id": "A-1", "amount": 20.0}), Level.LOW),
    (Action("issue_refund", {"order_id": "A-1", "amount": 250.0}), Level.MEDIUM),
    (Action("issue_refund", {"order_id": "A-1", "amount": 1249.0}), Level.HIGH),
    (Action("send_email", {"to": "ops@acme.example", "subject": "s", "body": "b"}), Level.LOW),
    (Action("send_email", {"to": "x@customer.example", "subject": "s", "body": "b"}), Level.MEDIUM),
    (Action("close_account", {"customer_id": "C-1", "purge_data": True}), Level.CRITICAL),
])
def test_risk_levels(action, level):
    assert RiskPolicy().assess(action, TOOL_SPECS[action.tool]).level is level


# ---------------------------------------------------------------- the safety properties

def test_risky_action_never_runs_before_approval(tmp_path):
    state = make_agent(tmp_path).start(TASK, "sam")
    assert state.status == "waiting_approval"
    assert state.pending.action.tool == "issue_refund"
    assert world(tmp_path) is None or world(tmp_path)["refunds"] == {}
    assert executed(tmp_path, "issue_refund") == []


def test_executor_refuses_unapproved_and_mismatched_actions(tmp_path):
    backoffice = Backoffice()
    executor = Executor(backoffice, RiskPolicy())
    refund = Action("issue_refund", {"order_id": "A-1042", "amount": 1249.0})
    with pytest.raises(PermissionError):
        executor.run(refund, "k1", approval=None)

    agent = make_agent(tmp_path)
    state = agent.start(TASK, "sam")
    request = agent.decide(state.id, "alice", True, "verified")
    assert request.status == "approved"
    bigger = Action("issue_refund", {"order_id": "A-1042", "amount": 9999.0})
    with pytest.raises(PermissionError):
        executor.run(bigger, "k2", approval=request)  # approval is bound to the exact arguments
    assert backoffice.state["refunds"] == {}


def test_decision_rules(tmp_path):
    agent = make_agent(tmp_path)
    state = agent.start(TASK, "sam")
    with pytest.raises(ApprovalError, match="cannot approve"):
        agent.decide(state.id, "sam", True, "mine")
    with pytest.raises(ApprovalError, match="written reason"):
        agent.decide(state.id, "alice", True, "")
    with pytest.raises(ApprovalError, match="different action"):
        state.pending.decide("alice", True, "ok", "0000000000000000", "t")


def test_critical_needs_two_distinct_approvers_and_one_no_wins(tmp_path):
    agent = make_agent(tmp_path)
    run_id = agent.start(TASK, "sam").id
    agent.decide(run_id, "alice", True, "verified")
    agent.resume(run_id)
    agent.decide(run_id, "alice", True, "ok")
    state = agent.resume(run_id)
    assert state.pending.risk.level is Level.CRITICAL

    request = agent.decide(run_id, "alice", True, "dup confirmed")
    assert request.status == "pending"
    with pytest.raises(ApprovalError, match="already decided"):
        agent.decide(run_id, "alice", True, "again")
    agent.decide(run_id, "bob", False, "open invoice")
    state = agent.resume(run_id)
    assert state.status == "done"
    assert world(tmp_path)["accounts"]["C-78"] == "active"
    assert "close_account: rejected" in state.answer


def test_rejection_is_fed_back_and_the_agent_adapts(tmp_path):
    agent = make_agent(tmp_path)
    run_id = agent.start(TASK, "sam").id
    agent.decide(run_id, "bob", False, "needs finance sign-off")
    state = agent.resume(run_id)
    assert state.pending.action.tool == "send_email"
    assert "escalated" in state.pending.action.args["body"]
    assert executed(tmp_path, "issue_refund") == []


def test_resume_in_a_fresh_process_does_not_repeat_finished_steps(tmp_path):
    run_id = make_agent(tmp_path).start(TASK, "sam").id
    fresh = make_agent(tmp_path)  # new objects, same disk: like a restarted server
    fresh.decide(run_id, "alice", True, "verified")
    state = fresh.resume(run_id)
    assert state.pending.action.tool == "send_email"
    assert len(executed(tmp_path, "lookup_order")) == 1
    assert len(executed(tmp_path, "issue_refund")) == 1


class CrashAfterSideEffect(Executor):
    crashed = False

    def run(self, action, idempotency_key, approval):
        result = super().run(action, idempotency_key, approval)
        if action.tool == "issue_refund" and not CrashAfterSideEffect.crashed:
            CrashAfterSideEffect.crashed = True
            raise RuntimeError("power cut after the refund, before the checkpoint")
        return result


def test_crash_between_side_effect_and_checkpoint_never_double_refunds(tmp_path):
    agent = make_agent(tmp_path, CrashAfterSideEffect)
    run_id = agent.start(TASK, "sam").id
    agent.decide(run_id, "alice", True, "verified")
    with pytest.raises(RuntimeError):
        agent.resume(run_id)
    assert agent.store.load(run_id).in_flight is not None  # intent was committed before the crash

    make_agent(tmp_path).resume(run_id)
    assert len(world(tmp_path)["refunds"]) == 1


def test_audit_chain_detects_tampering(tmp_path):
    agent = make_agent(tmp_path)
    run_id = agent.start(TASK, "sam").id
    agent.decide(run_id, "alice", True, "verified")
    agent.resume(run_id)
    log = AuditLog(tmp_path / "audit.jsonl")
    assert log.verify() == (True, "audit chain intact")

    lines = log.path.read_text().splitlines()
    lines[2] = lines[2].replace("lookup_order", "issue_refund")
    log.path.write_text("\n".join(lines) + "\n")
    ok, message = log.verify()
    assert not ok and "entry 3" in message
