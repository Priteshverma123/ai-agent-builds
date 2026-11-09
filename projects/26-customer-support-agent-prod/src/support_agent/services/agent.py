"""The agent loop: model decides -> tool runs -> result goes back -> repeat, inside a trace.

Production behaviours worth noticing:
* a hard step budget (and an automatic escalation when it runs out),
* citations are checked against the policy index, never trusted blindly,
* once a conversation is handed to a human, the bot stops talking,
* conversations are bound to the customer that started them.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field

from ..adapters.llm import LLM
from ..config import Settings
from ..domain.models import (Citation, Conversation, Message, RefundStatus, TicketKind,
                             TicketStatus, ToolRecord, Ticket)
from ..observability import TraceRecorder, TraceStore, log_event
from .retrieval import PolicyIndex
from .tools import SupportTools, ToolContext

CITATION = re.compile(r"\[([\w.-]+\.md#[\w-]+)\]")

SYSTEM_PROMPT = """You are the customer support assistant for Northwind Goods.
Rules:
- Use tools for every fact about orders, shipping and refunds. Never invent order data.
- Refund outcomes come from the issue_refund tool. Report them; do not override them.
- Answer policy questions only from search_policy results and cite chunk ids like [refunds.md#refund-window].
- If the customer asks for a human or is upset, call escalate_to_human.
Customer: {customer_id}. Today: {today}. Known order: {known_order}."""


class ConversationForbidden(Exception):
    """Raised when a customer tries to continue someone else's conversation."""


@dataclass
class TurnResult:
    conversation_id: str
    reply: str
    trace_id: str
    citations: list[Citation] = field(default_factory=list)
    tools: list[ToolRecord] = field(default_factory=list)
    escalated: bool = False
    ticket_id: str | None = None


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, Conversation] = {}

    def get_or_create(self, conversation_id: str | None, customer_id: str) -> Conversation:
        with self._lock:
            if conversation_id and conversation_id in self._items:
                conv = self._items[conversation_id]
                if conv.customer_id != customer_id:
                    raise ConversationForbidden(conversation_id)
                return conv
            conv = Conversation(conversation_id=conversation_id or f"conv_{uuid.uuid4().hex[:10]}",
                                customer_id=customer_id)
            self._items[conv.conversation_id] = conv
            return conv

    def get(self, conversation_id: str) -> Conversation | None:
        return self._items.get(conversation_id)


class SupportAgent:
    def __init__(self, llm: LLM, tools: SupportTools, index: PolicyIndex, traces: TraceStore,
                 settings: Settings) -> None:
        self.llm, self.tools, self.index, self.traces, self.settings = llm, tools, index, traces, settings
        self.conversations = ConversationStore()

    def handle(self, customer_id: str, text: str, conversation_id: str | None = None) -> TurnResult:
        conv = self.conversations.get_or_create(conversation_id, customer_id)
        conv.turns += 1
        conv.messages.append(Message(role="user", content=text))
        rec = TraceRecorder(conv.conversation_id)
        with rec.span("agent.turn", turn=conv.turns, customer_id=customer_id) as turn:
            if conv.escalated:
                reply = (f"Your conversation is with our support team (ticket {conv.ticket_id}). "
                         f"A person will reply here; I've added your message to the ticket.")
                result = TurnResult(conv.conversation_id, reply, rec.trace.trace_id, escalated=True,
                                    ticket_id=conv.ticket_id)
            else:
                result = self._run_loop(conv, rec)
            turn["tools"] = [t.name for t in result.tools]
            turn["escalated"] = result.escalated
        conv.messages.append(Message(role="assistant", content=result.reply))
        self.traces.save(rec.trace)
        log_event("chat.turn", trace_id=rec.trace.trace_id, conversation_id=conv.conversation_id,
                  customer_id=customer_id, tools=[t.name for t in result.tools], escalated=result.escalated,
                  citations=[c.chunk_id for c in result.citations])
        return result

    def _run_loop(self, conv: Conversation, rec: TraceRecorder) -> TurnResult:
        ctx = ToolContext(conv.conversation_id, conv.customer_id)
        system = SYSTEM_PROMPT.format(customer_id=conv.customer_id, today=self.settings.current_date(),
                                      known_order=conv.known_order_id or "none")
        records: list[ToolRecord] = []
        ticket_id: str | None = None
        for step in range(1, self.settings.max_agent_steps + 1):
            with rec.span("llm.complete", step=step, provider=self.llm.name) as attrs:
                response = self.llm.complete(system, conv.messages, self.tools.schemas())
                attrs["thought"] = response.thought
                attrs["decision"] = [c.name for c in response.tool_calls] or "final_answer"
            if not response.tool_calls:
                return TurnResult(conv.conversation_id, response.text, rec.trace.trace_id,
                                  citations=self._citations(response.text, rec), tools=records,
                                  escalated=conv.escalated, ticket_id=ticket_id or conv.ticket_id)
            conv.messages.append(Message(role="assistant", content=response.text, tool_calls=response.tool_calls,
                                         provider_content=response.provider_content))
            for call in response.tool_calls:
                with rec.span(f"tool.{call.name}", args=call.args) as attrs:
                    result = self.tools.execute(call.name, call.args, ctx)
                    attrs.update(ok=result.ok, summary=result.summary)
                log_event("tool.call", trace_id=rec.trace.trace_id, tool=call.name, ok=result.ok,
                          summary=result.summary)
                records.append(ToolRecord(name=call.name, args=call.args, ok=result.ok, summary=result.summary))
                conv.messages.append(Message(role="tool", content=json.dumps(result.data),
                                             tool_call_id=call.call_id, tool_name=call.name))
                ticket_id = self._update_state(conv, call.name, result.ok, result.data) or ticket_id
        return self._budget_exhausted(conv, ctx, rec, records)

    def _update_state(self, conv: Conversation, tool: str, ok: bool, data: dict) -> str | None:
        """Remember facts across turns; return a ticket id if this tool created one."""
        if tool == "get_order" and ok:
            conv.known_order_id = data["order_id"]
        if tool == "escalate_to_human" and ok:
            conv.escalated, conv.ticket_id = True, data["ticket_id"]
            return data["ticket_id"]
        if tool == "issue_refund" and data.get("status") == RefundStatus.PENDING_APPROVAL.value:
            return data["ticket_id"]
        return None

    def _budget_exhausted(self, conv: Conversation, ctx: ToolContext, rec: TraceRecorder,
                          records: list[ToolRecord]) -> TurnResult:
        with rec.span("guard.step_budget", max_steps=self.settings.max_agent_steps):
            result = self.tools.execute("escalate_to_human", {"reason": "agent step budget exhausted"}, ctx)
        conv.escalated, conv.ticket_id = True, result.data["ticket_id"]
        reply = f"Let me get a teammate to help with this one (ticket {conv.ticket_id})."
        return TurnResult(conv.conversation_id, reply, rec.trace.trace_id, tools=records,
                          escalated=True, ticket_id=conv.ticket_id)

    def _citations(self, text: str, rec: TraceRecorder) -> list[Citation]:
        """Keep only citations that point at a real policy chunk; log any the model made up."""
        found: list[Citation] = []
        with rec.span("guard.citations") as attrs:
            for chunk_id in dict.fromkeys(CITATION.findall(text)):
                chunk = self.index.get(chunk_id)
                if chunk is None:
                    attrs.setdefault("dropped", []).append(chunk_id)
                    continue
                found.append(Citation(chunk_id=chunk_id, title=chunk.title, snippet=chunk.text[:160]))
            attrs["kept"] = [c.chunk_id for c in found]
        return found

    def resolve_ticket(self, ticket_id: str, approve: bool, agent: str) -> Ticket:
        """A human approves or rejects a queued refund (or closes an escalation)."""
        ticket = self.tools.queue.get(ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        if ticket.kind is TicketKind.ESCALATION:
            return self.tools.queue.resolve(ticket_id, TicketStatus.CLOSED, agent)
        status = TicketStatus.APPROVED if approve else TicketStatus.REJECTED
        ticket = self.tools.queue.resolve(ticket_id, status, agent)
        note = f"Update from {agent}: your refund request ({ticket_id}) was {status.value}."
        if approve:
            refund_id = self.tools.ledger.record(ticket.payload["order_id"], ticket.payload["amount"], agent)
            ticket.payload["refund_id"] = refund_id
            note += f" Refund {refund_id} is on its way."
        conv = self.conversations.get(ticket.conversation_id)
        if conv is not None:
            conv.messages.append(Message(role="assistant", content=note))
        log_event("ticket.resolved", ticket_id=ticket_id, status=status.value, agent=agent)
        return ticket
