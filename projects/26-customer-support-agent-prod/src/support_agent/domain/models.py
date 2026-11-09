"""Domain objects: plain pydantic models with no I/O and no framework imports."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


class Order(BaseModel):
    order_id: str
    customer_id: str
    status: OrderStatus
    items: list[str]
    total: float
    currency: str = "USD"
    final_sale: bool = False
    delivered_on: date | None = None
    tracking_id: str | None = None


class Shipment(BaseModel):
    tracking_id: str
    carrier: str
    status: str
    eta: date | None = None
    last_event: str


class RefundStatus(str, Enum):
    APPROVED = "approved"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"


class RefundDecision(BaseModel):
    """What the refund policy says about one request. Produced by code, never by the LLM."""

    status: RefundStatus
    reason: str
    amount: float
    policy_ref: str


class TicketKind(str, Enum):
    ESCALATION = "escalation"
    REFUND_APPROVAL = "refund_approval"


class TicketStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class Ticket(BaseModel):
    ticket_id: str
    kind: TicketKind
    conversation_id: str
    customer_id: str
    reason: str
    status: TicketStatus = TicketStatus.OPEN
    payload: dict[str, Any] = Field(default_factory=dict)
    resolved_by: str | None = None


class ToolCall(BaseModel):
    call_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """One entry of the transcript the model sees."""

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    provider_content: Any = None  # a real provider's raw assistant blocks, replayed unchanged


class LLMResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thought: str = ""  # MockLLM explains itself; real providers usually leave this empty
    provider_content: Any = None


class Citation(BaseModel):
    chunk_id: str
    title: str
    snippet: str


class ToolRecord(BaseModel):
    """What the API reports back about each tool call in a turn."""

    name: str
    args: dict[str, Any]
    ok: bool
    summary: str


class Conversation(BaseModel):
    """Per-conversation state that survives between /chat calls."""

    conversation_id: str
    customer_id: str
    messages: list[Message] = Field(default_factory=list)
    known_order_id: str | None = None
    escalated: bool = False
    ticket_id: str | None = None
    turns: int = 0
