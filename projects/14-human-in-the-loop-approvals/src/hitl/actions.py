"""Actions, tool specs and the fake back office the agent operates on."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Action:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """A stable hash of tool + args. An approval is bound to this exact action, nothing else."""
        canonical = json.dumps({"tool": self.tool, "args": self.args}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def describe(self) -> str:
        args = ", ".join(f"{k}={_short(v)!r}" for k, v in self.args.items())
        return f"{self.tool}({args})"

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": self.args}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(data["tool"], dict(data.get("args", {})))


def _short(value: Any, limit: int = 32) -> Any:
    text = str(value)
    return value if len(text) <= limit else text[: limit - 3] + "..."


@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: str
    base_risk: int
    reversible: bool = True
    description: str = ""


TOOL_SPECS: dict[str, ToolSpec] = {
    s.name: s
    for s in (
        ToolSpec("lookup_order", "read", 5, description="lookup_order(order_id) -> order details"),
        ToolSpec("issue_refund", "payments", 25, description="issue_refund(order_id, amount) -> refund id"),
        ToolSpec("send_email", "communication", 15, description="send_email(to, subject, body)"),
        ToolSpec("close_account", "account admin", 40, reversible=False,
                 description="close_account(customer_id, purge_data) -> closes and optionally deletes data"),
    )
}


class Backoffice:
    """The 'real world': orders, a payments ledger, an outbox and accounts, persisted to JSON.

    Every write takes an idempotency key. Replaying the same key returns the first result instead of
    doing the work twice, which is what makes resume-after-crash safe.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.state: dict[str, Any] = {
            "orders": {"A-1042": {"customer_id": "C-77", "email": "dana@customer.example",
                                  "amount": 1249.0, "times_charged": 2, "duplicate_account": "C-78"}},
            "accounts": {"C-77": "active", "C-78": "active"},
            "refunds": {}, "outbox": [], "done": {},
        }
        if path and path.exists():
            self.state = json.loads(path.read_text(encoding="utf-8"))

    def _once(self, key: str, work: Any) -> str:
        if key in self.state["done"]:
            return self.state["done"][key]
        result = work()
        self.state["done"][key] = result
        self._save()
        return result

    def _save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def lookup_order(self, order_id: str, idempotency_key: str = "") -> str:
        order = self.state["orders"].get(order_id)
        return json.dumps({"order_id": order_id, **order}) if order else f"no order {order_id}"

    def issue_refund(self, order_id: str, amount: float, idempotency_key: str) -> str:
        def work() -> str:
            refund_id = f"rf_{len(self.state['refunds']) + 1:04d}"
            self.state["refunds"][refund_id] = {"order_id": order_id, "amount": amount}
            return f"refund {refund_id} of {amount:.2f} issued for {order_id}"
        return self._once(idempotency_key, work)

    def send_email(self, to: str, subject: str, body: str, idempotency_key: str) -> str:
        def work() -> str:
            self.state["outbox"].append({"to": to, "subject": subject, "body": body})
            return f"email '{subject}' sent to {to}"
        return self._once(idempotency_key, work)

    def close_account(self, customer_id: str, purge_data: bool, idempotency_key: str) -> str:
        def work() -> str:
            self.state["accounts"][customer_id] = "purged" if purge_data else "closed"
            return f"account {customer_id} {self.state['accounts'][customer_id]}"
        return self._once(idempotency_key, work)
