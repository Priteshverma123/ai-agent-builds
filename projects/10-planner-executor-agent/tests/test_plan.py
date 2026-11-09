import pytest

from planner_executor import Plan, PlanError, Step, diff_plans, parse_plan, resolve

TOOLS = {"search", "book"}


def test_resolve_follows_dotted_references():
    outputs = {"s1": [{"id": "H-1"}, {"id": "H-2"}], "s2": {"confirmation": "C-9"}}
    assert resolve("$s1.1.id", outputs) == "H-2"
    assert resolve(["$s2.confirmation", "plain"], outputs) == ["C-9", "plain"]


def test_parse_plan_rejects_unknown_tools():
    with pytest.raises(PlanError, match="unknown tool"):
        parse_plan({"steps": [{"id": "s1", "tool": "delete_everything", "args": {}}]}, 1, TOOLS)


def test_parse_plan_rejects_forward_references():
    data = {"steps": [{"id": "s1", "tool": "book", "args": {"x": "$s2.0.id"}},
                      {"id": "s2", "tool": "search", "args": {}}]}
    with pytest.raises(PlanError, match="not an earlier step"):
        parse_plan(data, 1, TOOLS)


def test_diff_marks_kept_changed_removed_and_added_steps():
    old = Plan(1, (Step("a", "search", {}), Step("b", "book", {"x": 1}), Step("c", "book", {"y": "$b.id"})))
    new = Plan(2, (Step("a", "search", {}), Step("b2", "book", {"x": 2}), Step("c", "book", {"y": "$b2.id"})))
    assert [(d.mark, d.step.id) for d in diff_plans(old, new)] == [("=", "a"), ("-", "b"), ("+", "b2"), ("~", "c")]
