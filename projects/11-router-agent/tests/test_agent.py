import pytest

from router_agent import BillingAgent, RouterAgent, SalesAgent, TechSupportAgent


def make_agent(router):
    return RouterAgent(router, [BillingAgent(), TechSupportAgent(), SalesAgent()])


def test_billing_specialist_finds_the_duplicate_charge(router):
    response = make_agent(router).handle("I was charged twice on invoice INV-1042")
    assert response.agent == "billing" and "refund" in response.reply


def test_fallback_asks_a_clarifying_question(router):
    response = make_agent(router).handle("I can't log in and I also want a refund")
    assert response.agent == "fallback" and "billing or tech support" in response.reply


def test_missing_specialist_is_caught_at_startup(router):
    with pytest.raises(ValueError, match="no specialist"):
        RouterAgent(router, [BillingAgent()])
