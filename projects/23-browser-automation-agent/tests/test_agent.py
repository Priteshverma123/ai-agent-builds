"""The observe -> act loop end to end with MockLLM."""

from browser_agent import Browser, BrowserAgent, MockLLM, ShopSite

GOAL = "Buy 2 Blue Ceramic Mugs with standard shipping for Ada Lovelace (ada@example.com)"


def test_agent_completes_checkout_and_recovers_from_validation_error():
    site = ShopSite()
    answer = BrowserAgent(Browser(site), MockLLM()).run(GOAL)
    assert "Order A1001: $24.00" in answer
    order = site.orders[0]
    assert order["items"] == {"MUG-BLUE": 2} and order["shipping"] == "standard"
    assert order["name"] == "Ada Lovelace" and order["terms"] == "yes"


def test_agent_uses_express_shipping_when_asked():
    site = ShopSite()
    BrowserAgent(Browser(site), MockLLM()).run(
        "Buy 1 Steel Travel Mug with express shipping for Grace Hopper (grace@example.com)")
    assert site.orders[0]["shipping"] == "express" and site.orders[0]["total"] == 33.5


def test_agent_reports_out_of_stock_instead_of_looping():
    site = ShopSite()
    answer = BrowserAgent(Browser(site), MockLLM()).run(
        "Buy 1 Red Ceramic Mug with standard shipping for Ada Lovelace (ada@example.com)")
    assert answer == "Red Ceramic Mug is out of stock." and site.orders == []


def test_agent_refuses_a_dialog_that_does_not_match_the_cart():
    site = ShopSite()
    original = site.confirm_text
    site.confirm_text = lambda template, form: original(template, form).replace("24.00", "240.00")  # a "dark pattern"
    answer = BrowserAgent(Browser(site), MockLLM(), max_steps=12).run(GOAL)
    assert site.orders == [] and answer.startswith("Stopped after 12 steps")


def test_step_limit_is_enforced():
    answer = BrowserAgent(Browser(ShopSite()), MockLLM(), max_steps=3).run(GOAL)
    assert answer == "Stopped after 3 steps without finishing."
