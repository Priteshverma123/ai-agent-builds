"""A tiny DOM: parse HTML (stdlib ``html.parser``) into a tree of ``Node`` objects we can query and mutate."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterator

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_CONTENT = {"script", "style", "template", "head"}


@dataclass(eq=False)  # identity matters: refs are attached to a specific node object
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)
    parent: "Node | None" = None
    ref: str | None = None  # assigned by the snapshot, cached so a node keeps its ref

    def iter(self) -> Iterator["Node"]:
        """All descendant elements, depth first."""
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.iter()

    def find_all(self, match: Callable[["Node"], bool]) -> list["Node"]:
        return [n for n in self.iter() if match(n)]

    def ancestor(self, tag: str) -> "Node | None":
        node = self.parent
        while node is not None and node.tag != tag:
            node = node.parent
        return node

    def text(self) -> str:
        """Visible text of this subtree, whitespace collapsed."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif not is_hidden(child):
                parts.append(child.text())
        return re.sub(r"\s+", " ", " ".join(parts)).strip()


def is_hidden(node: Node) -> bool:
    style = node.attrs.get("style", "").replace(" ", "").lower()
    return ("hidden" in node.attrs or node.attrs.get("aria-hidden") == "true" or "display:none" in style
            or (node.tag == "input" and node.attrs.get("type") == "hidden"))


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.stack = [self.root]
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_CONTENT:
            self.skipping += 1
            return
        if self.skipping:
            return
        node = Node(tag, {k: v if v is not None else "" for k, v in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and not self.skipping and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_CONTENT:
            self.skipping = max(0, self.skipping - 1)
            return
        if self.skipping:
            return
        for i in range(len(self.stack) - 1, 0, -1):  # forgive missing end tags: pop up to the match
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if not self.skipping and data.strip():
            self.stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def parse_page(html: str) -> Node:
    """Parse a full page. ``<title>`` lives in ``<head>``, which the tree skips, so read it from the source."""
    document = parse_html(html)
    title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    document.attrs["title"] = html_lib.unescape(" ".join(title.group(1).split())) if title else ""
    return document
