"""The human queue: where escalations and refund approvals wait for a person.

Swap this for Zendesk, Salesforce Service Cloud or a Slack channel in a real deployment.
"""

from __future__ import annotations

import threading
from typing import Any

from ..domain.models import Ticket, TicketKind, TicketStatus


class HumanQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tickets: dict[str, Ticket] = {}

    def open(self, kind: TicketKind, conversation_id: str, customer_id: str, reason: str,
             payload: dict[str, Any] | None = None) -> Ticket:
        with self._lock:
            ticket = Ticket(ticket_id=f"T-{len(self._tickets) + 1:04d}", kind=kind,
                            conversation_id=conversation_id, customer_id=customer_id,
                            reason=reason, payload=payload or {})
            self._tickets[ticket.ticket_id] = ticket
            return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def list(self, status: TicketStatus | None = None) -> list[Ticket]:
        with self._lock:
            return [t for t in self._tickets.values() if status is None or t.status == status]

    def resolve(self, ticket_id: str, status: TicketStatus, agent: str) -> Ticket:
        with self._lock:
            ticket = self._tickets[ticket_id]
            if ticket.status is not TicketStatus.OPEN:
                raise ValueError(f"{ticket_id} is already {ticket.status.value}")
            ticket.status, ticket.resolved_by = status, agent
            return ticket
