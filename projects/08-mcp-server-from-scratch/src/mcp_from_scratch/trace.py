"""Terminal trace helpers: plain ASCII so it renders in any terminal (and on video)."""

from __future__ import annotations

import json
import textwrap
from typing import Any

WIDTH = 92


def box(title: str, lines: list[str] | None = None) -> None:
    print("+" + "-" * (WIDTH - 2) + "+")
    print(f"| {title:<{WIDTH - 4}} |")
    for line in lines or []:
        print(f"| {line:<{WIDTH - 4}} |")
    print("+" + "-" * (WIDTH - 2) + "+")


def row(tag: str, text: str) -> None:
    """Print ``[tag   ] text`` with continuation lines aligned under the text."""
    prefix = f"[{tag:<6}] "
    wrapped = textwrap.wrap(text, WIDTH - len(prefix)) or [""]
    print(prefix + wrapped[0])
    for line in wrapped[1:]:
        print(" " * len(prefix) + line)


def wire(direction: str, message: dict[str, Any], limit: int = WIDTH - 9) -> None:
    """Show a JSON-RPC message as it travels: ``-->`` client to server, ``<--`` server to client."""
    text = json.dumps(message, separators=(",", ":"))
    row(direction, text if len(text) <= limit else text[: limit - 3] + "...")
