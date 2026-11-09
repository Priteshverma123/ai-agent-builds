"""Refund policy as code.

The single most important production rule in this project: the LLM may *ask* for a refund,
but only this pure function decides whether money moves. Prompts can be talked around;
an if-statement cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Order, OrderStatus, RefundDecision, RefundStatus


@dataclass(frozen=True)
class RefundPolicy:
    window_days: int = 30
    auto_approve_limit: float = 200.0


def evaluate_refund(
    order: Order,
    amount: float,
    already_refunded: float,
    today: date,
    policy: RefundPolicy,
) -> RefundDecision:
    """Return approved / pending_approval / denied with a human-readable reason."""

    def deny(reason: str, ref: str) -> RefundDecision:
        return RefundDecision(status=RefundStatus.DENIED, reason=reason, amount=amount, policy_ref=ref)

    if amount <= 0:
        return deny("Refund amount must be positive.", "refunds.md#how-refunds-work")
    if order.status is not OrderStatus.DELIVERED or order.delivered_on is None:
        return deny("Order has not been delivered yet; it can be cancelled instead of refunded.",
                    "refunds.md#eligibility")
    if order.final_sale:
        return deny("Final-sale items are not refundable.", "refunds.md#final-sale-items")
    age = (today - order.delivered_on).days
    if age > policy.window_days:
        return deny(f"Delivered {age} days ago; refunds are only possible within "
                    f"{policy.window_days} days of delivery.", "refunds.md#refund-window")
    remaining = round(order.total - already_refunded, 2)
    if amount > remaining:
        return deny(f"Requested {amount:.2f} exceeds the refundable balance of {remaining:.2f}.",
                    "refunds.md#how-refunds-work")
    if amount > policy.auto_approve_limit:
        return RefundDecision(
            status=RefundStatus.PENDING_APPROVAL,
            reason=f"Amounts above {policy.auto_approve_limit:.0f} need a human approver.",
            amount=amount,
            policy_ref="refunds.md#approvals",
        )
    return RefundDecision(status=RefundStatus.APPROVED, reason="Within policy.", amount=amount,
                          policy_ref="refunds.md#how-refunds-work")
