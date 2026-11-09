"""Agent cards, the task state machine, multi-turn input and JSON-RPC errors."""

import pytest

from a2a_local import A2AError, TaskState


def test_agent_card_is_served_at_well_known_path(fx):
    raw = fx.http.get("/.well-known/agent-card.json").json()
    assert raw["name"] == "FX Desk" and raw["preferredTransport"] == "JSONRPC"
    assert raw["skills"][0]["id"] == "convert_currency"
    assert fx.get_card().skills[0].tags[0] == "currency"


def test_blocking_send_completes_with_data_artifact(fx):
    fx.get_card()
    task = fx.send("Convert 100 USD to EUR")
    assert task.status.state == TaskState.completed
    data = task.artifacts[0].parts[0].data
    assert data == {"amount": 100.0, "from": "USD", "to": "EUR", "result": 92.0, "rate": 0.92}
    assert [m.role for m in task.history] == ["user", "agent"]


def test_input_required_then_follow_up_on_same_task(fx):
    fx.get_card()
    first = fx.send("Convert 500 dollars to JPY")
    assert first.status.state == TaskState.input_required
    assert "USD, CAD, AUD" in first.status.message.text
    second = fx.send("CAD", task_id=first.id, context_id=first.contextId)
    assert second.id == first.id and second.contextId == first.contextId
    assert second.status.state == TaskState.completed
    assert second.artifacts[0].parts[0].data["from"] == "CAD"
    assert len(second.history) == 4  # user, agent question, user answer, agent result


def test_non_blocking_send_then_poll(weather):
    weather.get_card()
    task = weather.send("What should I pack for Reykjavik in January?", blocking=False)
    assert task.status.state == TaskState.working  # returned before the slow agent finished
    done = weather.wait(task.id)
    assert done.status.state == TaskState.completed
    assert "a warm jacket" in done.artifacts[0].parts[1].data["pack"]


def test_unknown_city_fails_cleanly(weather):
    weather.get_card()
    task = weather.send("Pack for Atlantis in May")
    assert task.status.state == TaskState.failed and "Tokyo" in task.status.message.text


def test_jsonrpc_and_a2a_errors(fx):
    fx.get_card()
    with pytest.raises(A2AError) as missing:
        fx.get_task("nope")
    assert missing.value.code == -32001  # TaskNotFound
    done = fx.send("Convert 1 GBP to USD")
    with pytest.raises(A2AError) as not_cancelable:
        fx.cancel(done.id)
    assert not_cancelable.value.code == -32002
    with pytest.raises(A2AError) as closed:
        fx.send("again", task_id=done.id)
    assert closed.value.code == -32602
    assert fx.http.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/list"}).json()["error"]["code"] == -32601
    bad = fx.http.post("/", json={"jsonrpc": "2.0", "id": 2, "method": "message/send", "params": {"message": {}}})
    assert bad.json()["error"]["code"] == -32602
    assert fx.http.post("/", content=b"{oops").json()["error"]["code"] == -32700


def test_cancel_a_working_task(weather):
    weather.get_card()
    task = weather.send("What should I pack for Tokyo in July?", blocking=False)
    assert weather.cancel(task.id).status.state == TaskState.canceled
    assert weather.wait(task.id).status.state == TaskState.canceled  # the worker respects the cancel
