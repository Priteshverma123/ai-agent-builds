from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from support_agent.api import create_app


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def chat(client, customer, message, conversation_id=None, **kwargs):
    return client.post("/chat", json={"customer_id": customer, "message": message,
                                      "conversation_id": conversation_id}, **kwargs)


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["llm_provider"] == "mock" and body["orders_loaded"] == 6


def test_chat_returns_reply_tools_citations_and_trace(client):
    body = chat(client, "C-100", "Can I get a refund for ORD-1001?").json()
    assert body["reply"].startswith("Done. I've refunded $59.98")
    assert [t["name"] for t in body["tool_calls"]] == ["get_order", "issue_refund"]
    assert body["citations"][0]["chunk_id"] == "refunds.md#how-refunds-work"

    trace = client.get(f"/traces/{body['trace_id']}").json()
    names = [s["name"] for s in trace["spans"]]
    assert names[0] == "agent.turn" and "tool.issue_refund" in names and names.count("llm.complete") == 3
    assert trace["conversation_id"] == body["conversation_id"]


def test_unknown_trace_is_404(client):
    assert client.get("/traces/nope").status_code == 404


@pytest.mark.parametrize("payload", [
    {"customer_id": "C-100", "message": ""},
    {"customer_id": "bob", "message": "hi"},
    {"customer_id": "C-100", "message": "x" * 2001},
])
def test_bad_requests_are_rejected(client, payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_conversation_cannot_be_hijacked(client):
    conv = chat(client, "C-100", "hello").json()["conversation_id"]
    assert chat(client, "C-200", "refund ORD-1001", conv).status_code == 403


def test_api_key_is_enforced_when_configured(settings):
    client = TestClient(create_app(replace(settings, api_key="s3cret")))
    assert chat(client, "C-100", "hi").status_code == 401
    assert chat(client, "C-100", "hi", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200  # health stays open for load balancers


def test_human_approves_a_queued_refund(client):
    body = chat(client, "C-200", "refund ORD-2001 please").json()
    ticket_id = body["ticket_id"]
    assert [t["ticket_id"] for t in client.get("/queue", params={"status": "open"}).json()] == [ticket_id]

    resolved = client.post(f"/queue/{ticket_id}/resolve", json={"approve": True, "agent": "maria"}).json()
    assert resolved["status"] == "approved" and resolved["payload"]["refund_id"] == "R-0001"
    again = client.post(f"/queue/{ticket_id}/resolve", json={"approve": True, "agent": "maria"})
    assert again.status_code == 409
    assert client.post("/queue/T-9999/resolve", json={"approve": True, "agent": "x"}).status_code == 404


def test_bot_hands_off_and_stays_quiet(client):
    first = chat(client, "C-200", "I want to speak to a human").json()
    assert first["escalated"] and first["ticket_id"] == "T-0001"
    second = chat(client, "C-200", "refund ORD-2001 now", first["conversation_id"]).json()
    assert second["tool_calls"] == [] and "support team" in second["reply"]
