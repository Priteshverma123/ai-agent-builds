"""Local "web servers" the simulated browser talks to. No network, no real browser.

``ShopSite``  a small dynamic shop (search, product, cart, checkout with validation, order).
``FileSite``  serves any folder of static .html files, so you can point the agent at your own pages.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@dataclass
class Response:
    status: int
    html: str
    redirect: str | None = None  # a 303 "see other" after a POST, like real servers do


class Site(Protocol):
    host: str

    def request(self, method: str, path: str, query: dict[str, str], form: dict[str, str]) -> Response: ...

    def confirm_text(self, template: str, form: dict[str, str]) -> str: ...


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


class ShopSite:
    host = "shop.local"

    def __init__(self, folder: Path = EXAMPLES / "site") -> None:
        self.folder = folder
        self.catalog = {p["sku"]: p for p in json.loads((folder / "catalog.json").read_text(encoding="utf-8"))}
        self.cart: dict[str, int] = {}
        self.orders: list[dict] = []

    # ---- helpers -------------------------------------------------------------------
    def _page(self, title: str, content: str, status: int = 200) -> Response:
        layout = (self.folder / "layout.html").read_text(encoding="utf-8")
        page = (layout.replace("{{title}}", _esc(title))
                      .replace("{{cart_count}}", str(sum(self.cart.values())))
                      .replace("{{content}}", content))
        return Response(status, page)

    def _total(self, shipping: str = "standard") -> float:
        items = sum(self.catalog[sku]["price"] * qty for sku, qty in self.cart.items())
        return items + (9.0 if shipping == "express" else 0.0)

    # ---- routes --------------------------------------------------------------------
    def request(self, method: str, path: str, query: dict[str, str], form: dict[str, str]) -> Response:
        if method == "GET" and path in ("/", "/index.html"):
            return self._page("Home", (self.folder / "index.html").read_text(encoding="utf-8"))
        if method == "GET" and path == "/search":
            return self._search(query.get("q", ""))
        if method == "GET" and path.startswith("/product/"):
            return self._product(path.split("/")[-1])
        if method == "POST" and path == "/cart/add":
            sku, qty = form.get("sku", ""), int(form.get("qty", "1"))
            if sku in self.catalog and not self.catalog[sku].get("out_of_stock"):
                self.cart[sku] = self.cart.get(sku, 0) + qty
            return Response(303, "", redirect="/cart")
        if method == "GET" and path == "/cart":
            return self._cart()
        if method == "GET" and path == "/checkout":
            return self._checkout({}, "")
        if method == "POST" and path == "/order":
            return self._order(form)
        return self._page("Not found", f"<h1>Page not found</h1><p>No page at {_esc(path)}.</p>", 404)

    def _search(self, q: str) -> Response:
        words = q.lower().split()
        hits = [p for p in self.catalog.values() if words and all(w.rstrip("s") in p["name"].lower() for w in words)]
        items = "".join(f'<li><a href="/product/{p["sku"]}">{_esc(p["name"])}</a> <span>${p["price"]:.2f}</span></li>'
                        for p in hits)
        body = f"<ul>{items}</ul>" if hits else "<p>No products match your search.</p>"
        return self._page("Search results", f'<h1>Results for "{_esc(q)}"</h1><p>{len(hits)} found</p>{body}')

    def _product(self, sku: str) -> Response:
        product = self.catalog.get(sku)
        if product is None:
            return self._page("Not found", "<h1>Product not found</h1>", 404)
        disabled = " disabled" if product.get("out_of_stock") else ""
        options = "".join(f'<option value="{n}">{n}</option>' for n in range(1, 6))
        return self._page(product["name"], f"""
            <h1>{_esc(product['name'])}</h1>
            <p>${product['price']:.2f}. {_esc(product['description'])}</p>
            <form action="/cart/add" method="post" aria-label="Add to cart">
              <input type="hidden" name="sku" value="{sku}">
              <label for="qty">Quantity</label>
              <select id="qty" name="qty">{options}</select>
              <button type="submit"{disabled}>Add to cart</button>
            </form>""")

    def _cart(self) -> Response:
        if not self.cart:
            return self._page("Cart", "<h1>Your cart</h1><p>Your cart is empty.</p>")
        rows = "".join(f"<li>{qty} x {_esc(self.catalog[sku]['name'])}: ${self.catalog[sku]['price'] * qty:.2f}</li>"
                       for sku, qty in self.cart.items())
        return self._page("Cart", f'<h1>Your cart</h1><ul>{rows}</ul><p>Subtotal: ${self._total():.2f}</p>'
                                  f'<a href="/checkout">Proceed to checkout</a>')

    def _checkout(self, values: dict[str, str], error: str, status: int = 200) -> Response:
        shipping = values.get("shipping", "standard")
        alert = f'<p role="alert">{_esc(error)}</p>' if error else ""
        checked = " checked" if values.get("terms") else ""
        sel = {s: " selected" if s == shipping else "" for s in ("standard", "express")}
        return self._page("Checkout", f"""
            <h1>Checkout</h1>{alert}
            <form action="/order" method="post" aria-label="Shipping details">
              <label for="name">Full name</label>
              <input id="name" name="name" required value="{_esc(values.get('name', ''))}">
              <label for="email">Email</label>
              <input id="email" name="email" type="email" required value="{_esc(values.get('email', ''))}">
              <label for="shipping">Shipping</label>
              <select id="shipping" name="shipping">
                <option value="standard"{sel['standard']}>Standard (free)</option>
                <option value="express"{sel['express']}>Express ($9.00)</option>
              </select>
              <label><input type="checkbox" name="terms" value="yes"{checked}> I accept the terms of sale</label>
              <button type="submit" data-confirm="Place order for ${{total}}?">Place order</button>
            </form>""", status)

    def _order(self, form: dict[str, str]) -> Response:
        if not self.cart:
            return self._page("Cart", "<h1>Your cart</h1><p>Your cart is empty.</p>", 409)
        if not form.get("name") or "@" not in form.get("email", ""):
            return self._checkout(form, "Please enter your full name and a valid email.", 422)
        if form.get("terms") != "yes":
            return self._checkout(form, "Please accept the terms of sale to place your order.", 422)
        number = f"A{1001 + len(self.orders)}"
        total = self._total(form.get("shipping", "standard"))
        self.orders.append({"number": number, "items": dict(self.cart), "total": total, **form})
        self.cart.clear()
        return self._page("Order confirmed", f"<h1>Order confirmed</h1><p>Thank you, {_esc(form['name'])}! "
                                             f"Order {number}: ${total:.2f}. A receipt was sent to {_esc(form['email'])}.</p>")

    def confirm_text(self, template: str, form: dict[str, str]) -> str:
        """Fill ``{total}`` in a button's ``data-confirm`` text (the browser asks the page for it)."""
        return template.replace("{total}", f"{self._total(form.get('shipping', 'standard')):.2f}")


class FileSite:
    """Serve a folder of static HTML files. Forms with method=get just navigate to their action."""

    host = "files.local"

    def __init__(self, folder: Path) -> None:
        self.folder = folder.resolve()

    def request(self, method: str, path: str, query: dict[str, str], form: dict[str, str]) -> Response:
        target = (self.folder / path.lstrip("/")).resolve()
        if self.folder not in target.parents or not target.is_file():  # no ../ escapes
            return Response(404, f"<title>Not found</title><h1>Not found</h1><p>{_esc(path)}</p>")
        return Response(200, target.read_text(encoding="utf-8"))

    def confirm_text(self, template: str, form: dict[str, str]) -> str:
        return template
