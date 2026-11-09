"""A simulated browser: loads pages from a ``Site``, keeps form state, follows links, submits forms.

Every action returns an ``ActionResult`` that already contains the *new* snapshot, so the agent
observes the effect of what it did in the same round trip (observe -> act -> observe).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from .a11y import RefRegistry, build_tree, render, role_of
from .dom import Node, parse_page
from .site import Site

TEXT_INPUTS = ("text", "email", "password", "number", "search")


class BrowserError(Exception):
    """Something the *agent* did wrong (stale ref, disabled button...). Reported back, never fatal."""


@dataclass
class ActionResult:
    ok: bool
    message: str
    snapshot: str

    def for_model(self) -> str:
        status = "OK" if self.ok else "ERROR"
        return f"{status}: {self.message}\n\n{self.snapshot}"


@dataclass
class Dialog:
    message: str
    on_accept: Callable[[], str]


class Browser:
    def __init__(self, site: Site) -> None:
        self.site = site
        self.refs = RefRegistry()
        self.url = ""
        self.status = 0
        self.document = Node("#document")
        self.history: list[str] = []
        self.dialog: Dialog | None = None

    # ---- loading ---------------------------------------------------------------------
    def _load(self, method: str, url: str, form: dict[str, str] | None = None) -> None:
        parts = urlsplit(url)
        response = self.site.request(method, parts.path or "/", dict(parse_qsl(parts.query)), form or {})
        if response.redirect:  # POST -> 303 -> GET, the classic "post/redirect/get"
            return self._load("GET", response.redirect)
        if self.url:
            self.history.append(self.url)
        self.url, self.status = url, response.status
        self.document = parse_page(response.html)

    def _resolve(self, href: str) -> str:
        absolute = urljoin(f"http://{self.site.host}{self.url or '/'}", href)
        parts = urlsplit(absolute)
        return parts.path + (f"?{parts.query}" if parts.query else "")

    # ---- observing -------------------------------------------------------------------
    def snapshot(self) -> str:
        header = [f"Page: {self.document.attrs.get('title', '')}  (http://{self.site.host}{self.url})"]
        if self.status >= 400:
            header.append(f"HTTP status: {self.status}")
        if self.dialog:
            header.append(f'- dialog "{self.dialog.message}" [modal]: use handle_dialog(accept=true|false)')
        tree = render(build_tree(self.document, self.refs))
        return "\n".join(header + tree)

    def _act(self, action: Callable[[], str]) -> ActionResult:
        try:
            message = action()
            return ActionResult(True, message, self.snapshot())
        except BrowserError as exc:
            return ActionResult(False, str(exc), self.snapshot())

    def _element(self, ref: str) -> Node:
        if self.dialog:
            raise BrowserError(f'A dialog is open ("{self.dialog.message}"). Call handle_dialog first.')
        node = self.refs.by_ref.get(ref)
        if node is None:
            raise BrowserError(f"Ref {ref} not found in the current page snapshot. Take a new snapshot and use its refs.")
        if "disabled" in node.attrs:
            raise BrowserError(f"Element {ref} is disabled.")
        return node

    # ---- actions (the agent's tools) -------------------------------------------------
    def navigate(self, url: str) -> ActionResult:
        def go() -> str:
            self.dialog = None
            self._load("GET", self._resolve(url))
            return f"Navigated to {self.url}"
        return self._act(go)

    def back(self) -> ActionResult:
        def go() -> str:
            if not self.history:
                raise BrowserError("No previous page.")
            previous = self.history.pop()
            self._load("GET", previous)
            self.history.pop()  # _load pushed the page we just left; going back must not grow history
            return f"Went back to {self.url}"
        return self._act(go)

    def click(self, ref: str) -> ActionResult:
        def go() -> str:
            node = self._element(ref)
            role = role_of(node)
            if role == "link":
                self._load("GET", self._resolve(node.attrs["href"]))
                return f"Clicked link, now at {self.url}"
            if role == "checkbox":
                return self._set_checked(node, "checked" not in node.attrs)
            if role == "button" and (form := node.ancestor("form")) is not None:
                if node.attrs.get("type", "submit") != "submit":
                    return "Clicked button (it does nothing on this page)."
                if template := node.attrs.get("data-confirm"):
                    self.dialog = Dialog(self.site.confirm_text(template, self._form_data(form)),
                                         lambda: self._submit(form))
                    return f'Clicked "{node.text()}". The page opened a confirmation dialog.'
                return self._submit(form)
            return f"Clicked {role or node.tag}; nothing happened."
        return self._act(go)

    def type(self, ref: str, text: str, submit: bool = False) -> ActionResult:
        def go() -> str:
            node = self._element(ref)
            if not (node.tag == "textarea" or (node.tag == "input" and node.attrs.get("type", "text") in TEXT_INPUTS)):
                raise BrowserError(f"Element {ref} is a {role_of(node)}, not a text field.")
            node.attrs["value"] = text
            if submit and (form := node.ancestor("form")) is not None:
                return f'Typed "{text}" and pressed Enter. ' + self._submit(form)
            return f'Typed "{text}" into {ref}.'
        return self._act(go)

    def select_option(self, ref: str, option: str) -> ActionResult:
        def go() -> str:
            node = self._element(ref)
            options = node.find_all(lambda n: n.tag == "option")
            if node.tag != "select" or not options:
                raise BrowserError(f"Element {ref} is not a dropdown.")
            wanted = option.strip().lower()
            match = next((o for o in options if wanted in (o.text().lower(), o.attrs.get("value", "").lower())), None)
            if match is None:
                raise BrowserError(f'No option "{option}". Options: {", ".join(o.text() for o in options)}.')
            for o in options:
                o.attrs.pop("selected", None)
            match.attrs["selected"] = ""
            return f'Selected "{match.text()}" in {ref}.'
        return self._act(go)

    def check(self, ref: str, checked: bool = True) -> ActionResult:
        def go() -> str:
            node = self._element(ref)
            if role_of(node) != "checkbox":
                raise BrowserError(f"Element {ref} is not a checkbox.")
            return self._set_checked(node, checked)
        return self._act(go)

    def handle_dialog(self, accept: bool) -> ActionResult:
        def go() -> str:
            if self.dialog is None:
                raise BrowserError("No dialog is open.")
            dialog, self.dialog = self.dialog, None
            if not accept:
                return f'Dismissed dialog "{dialog.message}".'
            return f'Accepted dialog "{dialog.message}". ' + dialog.on_accept()
        return self._act(go)

    # ---- forms -----------------------------------------------------------------------
    @staticmethod
    def _set_checked(node: Node, checked: bool) -> str:
        if checked:
            node.attrs["checked"] = ""
        else:
            node.attrs.pop("checked", None)
        return f"Checkbox is now {'checked' if checked else 'unchecked'}."

    @staticmethod
    def _form_data(form: Node) -> dict[str, str]:
        """Collect fields the way a browser does: named inputs, checked boxes, selected options."""
        data: dict[str, str] = {}
        for field in form.find_all(lambda n: n.tag in ("input", "select", "textarea") and "name" in n.attrs):
            kind = field.attrs.get("type", "text")
            if field.tag == "select":
                options = field.find_all(lambda n: n.tag == "option")
                chosen = next((o for o in options if "selected" in o.attrs), options[0] if options else None)
                if chosen is not None:
                    data[field.attrs["name"]] = chosen.attrs.get("value", chosen.text())
            elif kind in ("checkbox", "radio"):
                if "checked" in field.attrs:
                    data[field.attrs["name"]] = field.attrs.get("value", "on")
            elif kind not in ("submit", "button", "reset"):
                data[field.attrs["name"]] = field.attrs.get("value", "")
        return data

    def _submit(self, form: Node) -> str:
        data = self._form_data(form)
        action = self._resolve(form.attrs.get("action", self.url))
        if form.attrs.get("method", "get").lower() == "post":
            self._load("POST", action, data)
        else:
            self._load("GET", f"{action.split('?')[0]}?{urlencode(data)}")
        return f"Submitted form, now at {self.url}" + (f" (HTTP {self.status})" if self.status >= 400 else "")
