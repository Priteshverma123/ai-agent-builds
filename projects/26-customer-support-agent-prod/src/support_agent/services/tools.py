"""The agent's tools. Each tool = a pydantic argument model + a handler + a JSON schema.

Two production rules are enforced here rather than in the prompt:
1. Identity comes from the authenticated session (ToolContext), never from model arguments.
2. Money-moving actions go through domain.policy.evaluate_refund.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from ..adapters.human_queue import HumanQueue
from ..adapters.repository import OrderRepository, RefundLedger
from ..domain.models import RefundStatus, TicketKind
from ..domain.policy import RefundPolicy, evaluate_refund
from .retrieval import PolicyIndex


@dataclass(frozen=True)
class ToolContext:
    conversation_id: str
    customer_id: str


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any]
    summary: str


class OrderArgs(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{4}$", description="Order number like ORD-1234")


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)


class RefundArgs(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{4}$")
    amount: float | None = Field(default=None, description="Omit for a full refund of the balance")
    reason: str = Field(default="customer request", max_length=300)


class EscalateArgs(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any, ToolContext], ToolResult]

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "input_schema": self.args_model.model_json_schema()}


class SupportTools:
    def __init__(self, repo: OrderRepository, ledger: RefundLedger, queue: HumanQueue,
                 index: PolicyIndex, policy: RefundPolicy, clock: Callable[[], date]) -> None:
        self.repo, self.ledger, self.queue, self.index = repo, ledger, queue, index
        self.policy, self.clock = policy, clock
        self.tools: dict[str, Tool] = {t.name: t for t in [
            Tool("get_order", "Look up one of the customer's orders.", OrderArgs, self.get_order),
            Tool("check_shipping", "Get carrier status and ETA for an order.", OrderArgs, self.check_shipping),
            Tool("search_policy", "Search store policies; returns citable chunks.", SearchArgs, self.search_policy),
            Tool("issue_refund", "Request a refund. Policy decides approve / pending / deny.",
                 RefundArgs, self.issue_refund),
            Tool("escalate_to_human", "Hand the conversation to a human agent.", EscalateArgs, self.escalate),
        ]}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def execute(self, name: str, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Validate arguments, run the handler, and turn every failure into data the model can read."""
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(False, {"error": f"unknown tool {name!r}"}, f"unknown tool {name}")
        try:
            args = tool.args_model.model_validate(raw_args)
        except ValidationError as exc:
            msg = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return ToolResult(False, {"error": f"invalid arguments: {msg}"}, "invalid arguments")
        return tool.handler(args, ctx)

    # --- handlers -------------------------------------------------------------------------

    def get_order(self, args: OrderArgs, ctx: ToolContext) -> ToolResult:
        order = self.repo.get_for_customer(args.order_id, ctx.customer_id)
        if order is None:
            return ToolResult(False, {"error": f"No order {args.order_id} on this account."}, "not found")
        data = order.model_dump(mode="json")
        data["refunded_so_far"] = self.ledger.refunded_total(order.order_id)
        return ToolResult(True, data, f"{order.status.value}, total {order.total:.2f}")

    def check_shipping(self, args: OrderArgs, ctx: ToolContext) -> ToolResult:
        order = self.repo.get_for_customer(args.order_id, ctx.customer_id)
        if order is None:
            return ToolResult(False, {"error": f"No order {args.order_id} on this account."}, "not found")
        shipment = self.repo.shipment(order.tracking_id) if order.tracking_id else None
        if shipment is None:
            return ToolResult(True, {"order_id": order.order_id, "status": "not shipped yet"}, "not shipped")
        data = shipment.model_dump(mode="json") | {"order_id": order.order_id}
        return ToolResult(True, data, f"{shipment.status}, eta {shipment.eta}")

    def search_policy(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        hits = self.index.search(args.query, k=3)
        data = {"results": [{"chunk_id": h.chunk.chunk_id, "title": h.chunk.title,
                             "text": h.chunk.text, "score": h.score} for h in hits]}
        return ToolResult(True, data, ", ".join(h.chunk.chunk_id for h in hits) or "no matches")

    def issue_refund(self, args: RefundArgs, ctx: ToolContext) -> ToolResult:
        order = self.repo.get_for_customer(args.order_id, ctx.customer_id)
        if order is None:
            return ToolResult(False, {"error": f"No order {args.order_id} on this account."}, "not found")
        refunded = self.ledger.refunded_total(order.order_id)
        amount = round(args.amount if args.amount is not None else order.total - refunded, 2)
        decision = evaluate_refund(order, amount, refunded, self.clock(), self.policy)
        data = decision.model_dump(mode="json") | {"order_id": order.order_id}
        if decision.status is RefundStatus.APPROVED:
            data["refund_id"] = self.ledger.record(order.order_id, amount, approved_by="policy-auto")
        elif decision.status is RefundStatus.PENDING_APPROVAL:
            ticket = self.queue.open(TicketKind.REFUND_APPROVAL, ctx.conversation_id, ctx.customer_id,
                                     reason=args.reason, payload={"order_id": order.order_id, "amount": amount})
            data["ticket_id"] = ticket.ticket_id
        return ToolResult(True, data, f"{decision.status.value} {amount:.2f}")

    def escalate(self, args: EscalateArgs, ctx: ToolContext) -> ToolResult:
        ticket = self.queue.open(TicketKind.ESCALATION, ctx.conversation_id, ctx.customer_id, args.reason)
        return ToolResult(True, {"ticket_id": ticket.ticket_id, "reason": args.reason}, ticket.ticket_id)
