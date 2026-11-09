"""Browser actions: forms, dialogs, and the errors the agent must be able to read and recover from."""

from conftest import ref_of


def test_search_form_submits_with_get(browser):
    snap = browser.navigate("/index.html").snapshot
    result = browser.type(ref_of(snap, "searchbox", "Search products"), "travel mug", submit=True)
    assert result.ok and browser.url == "/search?q=travel+mug"
    assert '- link "Steel Travel Mug"' in result.snapshot


def test_stale_ref_is_a_readable_error_not_a_crash(browser):
    old = browser.navigate("/index.html").snapshot
    browser.navigate("/cart")
    result = browser.click(ref_of(old, "link", "Steel Travel Mug"))
    assert not result.ok and "not found in the current page snapshot" in result.message
    assert result.snapshot.startswith("Page: Cart")  # the error still shows where we are


def test_disabled_and_wrong_element_errors(browser):
    snap = browser.navigate("/product/MUG-RED").snapshot
    assert "[disabled]" in snap
    assert "disabled" in browser.click(ref_of(snap, "button", "Add to cart")).message
    assert "not a text field" in browser.type(ref_of(snap, "link", "Home"), "hi").message
    assert 'No option "9"' in browser.select_option(ref_of(snap, "combobox", "Quantity"), "9").message


def test_post_redirect_get_and_cart(browser, shop):
    snap = browser.navigate("/product/MUG-TRAVEL").snapshot
    browser.select_option(ref_of(snap, "combobox", "Quantity"), "3")
    result = browser.click(ref_of(snap, "button", "Add to cart"))
    assert browser.url == "/cart" and shop.cart == {"MUG-TRAVEL": 3}
    assert "Subtotal: $73.50" in result.snapshot


def test_dialog_blocks_other_actions_until_handled(browser, shop):
    shop.cart["MUG-BLUE"] = 1
    snap = browser.navigate("/checkout").snapshot
    browser.click(ref_of(snap, "button", "Place order"))
    blocked = browser.type(ref_of(snap, "textbox", "Full name"), "Ada")
    assert not blocked.ok and "A dialog is open" in blocked.message
    assert '- dialog "Place order for $12.00?" [modal]' in blocked.snapshot
    dismissed = browser.handle_dialog(accept=False)
    assert dismissed.ok and shop.orders == [] and "dialog" not in dismissed.snapshot


def test_server_validation_shows_an_alert_and_keeps_values(browser, shop):
    shop.cart["MUG-BLUE"] = 1
    snap = browser.navigate("/checkout").snapshot
    browser.type(ref_of(snap, "textbox", "Full name"), "Ada Lovelace")
    browser.type(ref_of(snap, "textbox", "Email"), "ada@example.com")
    browser.click(ref_of(snap, "button", "Place order"))
    result = browser.handle_dialog(accept=True)
    assert browser.status == 422 and "- alert:" in result.snapshot
    assert "accept the terms" in result.snapshot
    assert '- textbox "Full name" [required] [ref=' in result.snapshot and ": Ada Lovelace" in result.snapshot


def test_static_file_site_links_forms_and_back(static_browser):
    snap = static_browser.navigate("/signup.html").snapshot
    static_browser.type(ref_of(snap, "textbox", "Your email"), "me@example.com")
    static_browser.click(ref_of(snap, "checkbox", "Weekly digest"))
    result = static_browser.click(ref_of(snap, "button", "Subscribe"))
    assert static_browser.url == "/thanks.html?email=me%40example.com&weekly=on&note="
    assert '- heading "You\'re subscribed"' in result.snapshot.replace("'", "'")
    assert static_browser.back().snapshot.startswith("Page: Newsletter signup")
    assert not static_browser.navigate("/../secrets.txt").snapshot.count("[ref=")
