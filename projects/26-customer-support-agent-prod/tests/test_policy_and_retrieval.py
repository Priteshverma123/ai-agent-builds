from datetime import date, timedelta

import pytest

from support_agent.domain.models import Order, OrderStatus, RefundStatus
from support_agent.domain.policy import RefundPolicy, evaluate_refund
from support_agent.services.retrieval import PolicyIndex, chunk_markdown

TODAY = date(2026, 10, 20)
POLICY = RefundPolicy(window_days=30, auto_approve_limit=200)


def order(**overrides) -> Order:
    base = dict(order_id="ORD-0001", customer_id="C-1", status=OrderStatus.DELIVERED, items=["x"],
                total=150.0, delivered_on=TODAY - timedelta(days=3))
    return Order(**(base | overrides))


@pytest.mark.parametrize("overrides, amount, refunded, expected, needle", [
    ({}, 150.0, 0, RefundStatus.APPROVED, "Within policy"),
    ({"total": 900.0}, 900.0, 0, RefundStatus.PENDING_APPROVAL, "human approver"),
    ({"delivered_on": TODAY - timedelta(days=31)}, 10, 0, RefundStatus.DENIED, "31 days"),
    ({"final_sale": True}, 10, 0, RefundStatus.DENIED, "Final-sale"),
    ({"status": OrderStatus.SHIPPED, "delivered_on": None}, 10, 0, RefundStatus.DENIED, "not been delivered"),
    ({}, 100.0, 60.0, RefundStatus.DENIED, "refundable balance of 90.00"),
    ({}, 0, 0, RefundStatus.DENIED, "positive"),
])
def test_refund_policy_table(overrides, amount, refunded, expected, needle):
    decision = evaluate_refund(order(**overrides), amount, refunded, TODAY, POLICY)
    assert decision.status is expected
    assert needle in decision.reason


def test_refund_window_boundary_is_inclusive():
    assert evaluate_refund(order(delivered_on=TODAY - timedelta(days=30)), 10, 0, TODAY, POLICY).status \
        is RefundStatus.APPROVED


def test_chunks_get_stable_citable_ids():
    chunks = chunk_markdown("faq.md", "# FAQ\n\n## Refund window\nThirty days.\n\n## Final sale\nNo refunds.\n")
    assert [c.chunk_id for c in chunks] == ["faq.md#refund-window", "faq.md#final-sale"]
    assert chunks[0].text == "Thirty days."


def test_search_ranks_the_relevant_policy_first(settings):
    index = PolicyIndex.from_dir(settings.data_dir / "policies")
    assert index.search("how long do I have to return something")[0].chunk.chunk_id == "refunds.md#refund-window"
    assert index.search("parcel lost late")[0].chunk.chunk_id == "shipping.md#lost-or-late-parcels"
    assert index.search("zzzz qqqq") == []
