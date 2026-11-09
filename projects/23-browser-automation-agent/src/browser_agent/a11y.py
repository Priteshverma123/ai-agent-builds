"""Accessibility snapshot: turn the DOM into the compact tree an agent actually reads.

Why not give the model raw HTML? It is long, noisy and full of layout. Screen readers solved this
decades ago: every element has a *role* (button, link, textbox), an accessible *name* and *states*.
We keep only meaningful nodes, flatten layout wrappers, drop hidden ones, and give every
interactive element a short ref like ``e7`` the model can point at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dom import Node, is_hidden

INPUT_ROLES = {"text": "textbox", "email": "textbox", "password": "textbox", "number": "spinbutton",
               "search": "searchbox", "checkbox": "checkbox", "radio": "radio",
               "submit": "button", "button": "button", "reset": "button"}
TAG_ROLES = {"button": "button", "select": "combobox", "textarea": "textbox", "nav": "navigation",
             "main": "main", "header": "banner", "footer": "contentinfo", "form": "form", "ul": "list",
             "ol": "list", "li": "listitem", "img": "img", "table": "table", "tr": "row",
             "td": "cell", "th": "columnheader", "section": "region", "aside": "complementary"}
INTERACTIVE = {"link", "button", "textbox", "searchbox", "spinbutton", "checkbox", "radio", "combobox"}
LEAF = INTERACTIVE | {"heading", "img"}  # their name already says everything; no children rendered
NAME_FROM_CONTENT = {"link", "button", "heading", "cell", "columnheader"}  # landmarks only use aria-label


def role_of(node: Node) -> str | None:
    if "role" in node.attrs:
        return node.attrs["role"]
    if node.tag == "a":
        return "link" if "href" in node.attrs else None
    if node.tag == "input":
        return INPUT_ROLES.get(node.attrs.get("type", "text"))
    if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return "heading"
    return TAG_ROLES.get(node.tag)


def accessible_name(node: Node, role: str, document: Node) -> str:
    """aria-label > <label for=id> > wrapping <label> > alt/title > text > placeholder."""
    if label := node.attrs.get("aria-label"):
        return label
    if node.attrs.get("id"):
        for label in document.find_all(lambda n: n.tag == "label" and n.attrs.get("for") == node.attrs["id"]):
            return label.text()
    if (wrapper := node.ancestor("label")) is not None:
        return wrapper.text()
    for attr in ("alt", "title"):
        if node.attrs.get(attr):
            return node.attrs[attr]
    if node.tag == "input" and node.attrs.get("type") in ("submit", "button"):
        return node.attrs.get("value", "Submit")
    if role in NAME_FROM_CONTENT and (text := node.text()):
        return text
    return node.attrs.get("placeholder", "")


def current_value(node: Node) -> str | None:
    if node.tag == "select":
        options = node.find_all(lambda n: n.tag == "option")
        chosen = next((o for o in options if "selected" in o.attrs), options[0] if options else None)
        return chosen.text() if chosen else ""
    if node.tag == "textarea":
        return node.attrs.get("value", node.text())
    if node.tag == "input" and node.attrs.get("type", "text") in ("text", "email", "password", "number", "search"):
        return node.attrs.get("value", "")
    return None


@dataclass
class AXNode:
    role: str
    name: str
    dom: Node
    ref: str | None = None
    props: list[str] = field(default_factory=list)
    value: str | None = None
    children: list["AXNode"] = field(default_factory=list)


class RefRegistry:
    """Hands out refs. A ref is cached on its DOM node, so the same element keeps the same ref."""

    def __init__(self) -> None:
        self.counter = 0
        self.by_ref: dict[str, Node] = {}

    def assign(self, node: Node) -> str:
        if node.ref is None:
            self.counter += 1
            node.ref = f"e{self.counter}"
        self.by_ref[node.ref] = node
        return node.ref


def build_tree(document: Node, refs: RefRegistry) -> list[AXNode]:
    refs.by_ref.clear()  # only refs from the *current* snapshot are valid

    def visit(node: Node | str) -> list[AXNode]:
        if isinstance(node, str):
            text = " ".join(node.split())
            return [AXNode("text", text, document)] if text else []
        if is_hidden(node) or node.tag == "option":
            return []  # options are listed on their combobox
        if node.tag == "label":  # its text becomes the input's name; keep only wrapped inputs
            return [ax for child in node.children if isinstance(child, Node) for ax in visit(child)]
        role = role_of(node)
        children = [] if role in LEAF else [c for child in node.children for c in visit(child)]
        if role is None:
            return children  # layout wrapper (div, span, p): promote its children
        ax = AXNode(role, accessible_name(node, role, document), node, children=children, value=current_value(node))
        if role in INTERACTIVE:
            ax.ref = refs.assign(node)
        if role == "heading":
            ax.props.append(f"level={node.tag[1]}")
        if role == "checkbox":
            ax.props.append("checked" if "checked" in node.attrs else "unchecked")
        if "disabled" in node.attrs:
            ax.props.append("disabled")
        if "required" in node.attrs:
            ax.props.append("required")
        if role == "combobox":
            ax.props.append("options: " + ", ".join(o.text() for o in node.find_all(lambda n: n.tag == "option")))
        if role in ("list", "listitem", "row", "cell", "form", "region") and not ax.children and not ax.name:
            return []
        return [ax]

    return [ax for child in document.children for ax in visit(child)]


def render(nodes: list[AXNode], indent: int = 0) -> list[str]:
    """YAML-ish lines: ``- role "name" [prop] [ref=eN]: value``."""
    lines = []
    for node in nodes:
        pad = "  " * indent
        if node.role == "text":
            lines.append(f'{pad}- text: {node.name}')
            continue
        name = node.name.replace('"', "'")
        line = f"{pad}- {node.role}" + (f' "{name}"' if name else "")
        line += "".join(f" [{p}]" for p in node.props)
        if node.ref:
            line += f" [ref={node.ref}]"
        if node.value:
            line += f": {node.value}"
        lines.append(line + (":" if node.children and node.value is None else ""))
        lines += render(node.children, indent + 1)
    return lines
