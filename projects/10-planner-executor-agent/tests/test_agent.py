import json

from conftest import GOAL
from planner_executor import MockPlannerLLM, PlanExecuteAgent, TravelWorld
from planner_executor import tools as tools_module


def test_agent_replans_around_a_sold_out_hotel_and_finishes():
    world = TravelWorld()
    result = PlanExecuteAgent(MockPlannerLLM(), world.tools()).run(GOAL)
    assert result.status == "done"
    assert len(result.plans) == 2
    assert [b["what"] for b in world.bookings] == ["TAP 07:05", "Baixa House x2 nights"]
    assert world.sent[0]["confirmations"] == ["CONF-FL-TP1351", "CONF-H-BAIXA"]


def test_completed_steps_are_not_run_twice():
    world = TravelWorld()
    result = PlanExecuteAgent(MockPlannerLLM(), world.tools()).run(GOAL)
    ran = [r.step_id for r in result.results]
    assert ran == ["s1", "s2", "s3", "s4", "s3b", "s4b", "s5"]
    assert len(world.bookings) == 2  # the flight was not booked again


def test_agent_gives_up_after_max_replans(monkeypatch):
    monkeypatch.setattr(tools_module, "SOLD_OUT", {"H-ALFAMA", "H-BAIXA", "H-AVENIDA"})
    world = TravelWorld()
    result = PlanExecuteAgent(MockPlannerLLM(), world.tools(), max_replans=2).run(GOAL)
    assert result.status == "failed" and "gave up" in result.reason
    assert world.sent == []  # nothing was emailed for a broken trip


class BadPlannerLLM:
    name = "bad"

    def complete(self, system, prompt):
        return json.dumps({"steps": [{"id": "s1", "tool": "wire_money", "args": {}}]})


def test_invalid_plan_is_rejected_before_any_tool_runs():
    world = TravelWorld()
    result = PlanExecuteAgent(BadPlannerLLM(), world.tools()).run(GOAL)
    assert result.status == "failed" and "unknown tool" in result.reason
    assert result.results == [] and world.bookings == []


def test_unrecoverable_error_aborts():
    world = TravelWorld()
    result = PlanExecuteAgent(MockPlannerLLM(), world.tools()).run(GOAL.replace("Lisbon", "Atlantis"))
    assert result.status == "aborted" and "no flights" in result.reason
    assert world.bookings == []
