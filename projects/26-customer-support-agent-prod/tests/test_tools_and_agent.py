from support_agent.domain.models import LLMResponse, TicketKind, ToolCall
from support_agent.services.tools import ToolContext
from support_agent.bootstrap import build_agent

CTX = ToolContext(conversation_id="conv_test", customer_id="C-100")


def test_tools_enforce_ownership(agent):
    result = agent.tools.execute("get_order", {"order_id": "ORD-2001"}, CTX)  # belongs to C-200
    assert not result.ok and "No order" in result.data["error"]


def test_invalid_arguments_become_readable_errors(agent):
    result = agent.tools.execute("issue_refund", {"order_id": "1001; DROP TABLE"}, CTX)
    assert not result.ok and result.data["error"].startswith("invalid arguments: order_id")
    assert agent.tools.execute("delete_everything", {}, CTX).summary == "unknown tool delete_everything"


def test_refunds_accumulate_in_the_ledger(agent):
    first = agent.tools.execute("issue_refund", {"order_id": "ORD-1001", "amount": 50}, CTX)
    second = agent.tools.execute("issue_refund", {"order_id": "ORD-1001", "amount": 20}, CTX)
    assert first.data["status"] == "approved"
    assert second.data["status"] == "denied" and "9.98" in second.data["reason"]


def test_large_refund_opens_an_approval_ticket(agent):
    ctx = ToolContext("conv_x", "C-200")
    result = agent.tools.execute("issue_refund", {"order_id": "ORD-2001"}, ctx)
    ticket = agent.tools.queue.get(result.data["ticket_id"])
    assert ticket.kind is TicketKind.REFUND_APPROVAL and ticket.payload["amount"] == 899.0
    assert agent.tools.ledger.entries() == []  # no money moved yet


def test_tool_schemas_are_exported_for_the_model(agent):
    names = {s["name"] for s in agent.tools.schemas()}
    assert names == {"get_order", "check_shipping", "search_policy", "issue_refund", "escalate_to_human"}
    refund = next(s for s in agent.tools.schemas() if s["name"] == "issue_refund")
    assert refund["input_schema"]["required"] == ["order_id"]


def test_state_carries_order_across_turns(agent):
    first = agent.handle("C-100", "I want a refund")
    assert "order number" in first.reply and first.tools == []
    second = agent.handle("C-100", "It's ORD-1001", first.conversation_id)
    assert second.conversation_id == first.conversation_id
    assert agent.conversations.get(first.conversation_id).known_order_id == "ORD-1001"


class LoopingLLM:
    """A misbehaving model that never stops calling tools."""

    name = "looping"

    def complete(self, system, messages, tools):
        return LLMResponse(tool_calls=[ToolCall(call_id="c", name="get_order", args={"order_id": "ORD-1001"})])


class InventingLLM:
    """A model that cites a policy section that does not exist."""

    name = "inventing"

    def complete(self, system, messages, tools):
        return LLMResponse(text="Refunds are instant [refunds.md#instant-refunds] [refunds.md#approvals]")


def test_step_budget_escalates_instead_of_looping_forever(settings):
    agent = build_agent(settings, LoopingLLM())
    result = agent.handle("C-100", "hello")
    assert result.escalated and result.ticket_id == "T-0001"
    assert len(result.tools) == settings.max_agent_steps


def test_invented_citations_are_dropped(settings):
    agent = build_agent(settings, InventingLLM())
    result = agent.handle("C-100", "are refunds instant?")
    assert [c.chunk_id for c in result.citations] == ["refunds.md#approvals"]
    guard = next(s for s in agent.traces.get(result.trace_id).spans if s.name == "guard.citations")
    assert guard.attrs["dropped"] == ["refunds.md#instant-refunds"]
