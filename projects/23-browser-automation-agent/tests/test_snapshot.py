"""The accessibility snapshot: roles, names, states, hidden content and ref stability."""

from conftest import ref_of

from browser_agent import parse_snapshot


def test_snapshot_has_roles_names_and_refs(browser):
    snap = browser.navigate("/index.html").snapshot
    assert snap.splitlines()[0] == "Page: Home | Mug Shop  (http://shop.local/index.html)"
    assert '- searchbox "Search products" [ref=e4]' in snap  # name from <label for=...>
    assert '- heading "Mugs for every desk" [level=1]' in snap
    assert '- navigation "Main":' in snap  # landmarks are named only by aria-label


def test_hidden_scripts_and_decorative_content_are_pruned(browser):
    snap = browser.navigate("/index.html").snapshot
    assert "Hidden 90% off" not in snap  # hidden attribute
    assert "analytics" not in snap  # <script> in <head>
    assert "- img" not in snap  # aria-hidden decorative image
    assert "<div" not in snap and "class=" not in snap  # layout is gone


def test_states_values_and_options(static_browser):
    snap = static_browser.navigate("/signup.html").snapshot
    assert '- textbox "Your email" [ref=' in snap
    assert '- checkbox "Weekly digest" [unchecked]' in snap  # input wrapped by its label
    assert '- button "Subscribe with SSO" [disabled]' in snap
    assert '- textbox "Anything else?"' in snap  # placeholder as last-resort name


def test_refs_are_stable_on_the_same_page_and_new_after_navigation(browser):
    first = browser.navigate("/index.html").snapshot
    again = browser.snapshot()
    assert ref_of(first, "searchbox", "Search products") == ref_of(again, "searchbox", "Search products")
    after = browser.click(ref_of(first, "link", "Steel Travel Mug")).snapshot
    assert ref_of(after, "link", "Home") != ref_of(first, "link", "Home")  # new page, new elements, new refs


def test_snapshot_text_round_trips_through_the_parser(browser):
    elements = parse_snapshot(browser.navigate("/product/MUG-BLUE").snapshot)
    quantity = next(e for e in elements if e.role == "combobox")
    assert quantity.name == "Quantity" and quantity.value == "1" and quantity.ref
    assert any(e.role == "text" and "$12.00" in e.name for e in elements)
