"""Data adapters. In production these wrap the order system, carrier API and payments API.

Here they are in-memory and loaded from examples/orders.json, behind the same small interfaces.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ..domain.models import Order, Shipment


class OrderRepository:
    def __init__(self, orders: list[Order], shipments: list[Shipment]) -> None:
        self._orders = {o.order_id: o for o in orders}
        self._shipments = {s.tracking_id: s for s in shipments}

    @classmethod
    def from_json(cls, path: Path) -> "OrderRepository":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            [Order.model_validate(o) for o in raw["orders"]],
            [Shipment.model_validate(s) for s in raw["shipments"]],
        )

    def get_for_customer(self, order_id: str, customer_id: str) -> Order | None:
        """Ownership check lives here: another customer's order looks exactly like a missing one."""
        order = self._orders.get(order_id.upper())
        return order if order and order.customer_id == customer_id else None

    def shipment(self, tracking_id: str) -> Shipment | None:
        return self._shipments.get(tracking_id)

    def __len__(self) -> int:
        return len(self._orders)


class RefundLedger:
    """Records money that actually moved. Thread-safe because FastAPI runs sync routes in a pool."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict] = []

    def refunded_total(self, order_id: str) -> float:
        with self._lock:
            return round(sum(e["amount"] for e in self._entries if e["order_id"] == order_id), 2)

    def record(self, order_id: str, amount: float, approved_by: str) -> str:
        with self._lock:
            refund_id = f"R-{len(self._entries) + 1:04d}"
            self._entries.append({"refund_id": refund_id, "order_id": order_id,
                                  "amount": amount, "approved_by": approved_by})
            return refund_id

    def entries(self) -> list[dict]:
        with self._lock:
            return list(self._entries)
