"""Plain-ASCII terminal rendering (safe on every console, no colour libraries)."""

from __future__ import annotations

import textwrap

from .agent import Event

WIDTH = 78
ICONS = {"model": "[model]", "tool": "[tool] ", "guard": "[GUARD]", "blocked": "[BLOCK]", "answer": "[done] "}


def box(title: str, lines: list[str], width: int = WIDTH) -> str:
    inner = width - 4
    out = [f"+-- {title} " + "-" * max(0, width - len(title) - 6) + "+"]
    for line in lines or [""]:
        for piece in textwrap.wrap(line, inner) or [""]:
            out.append(f"| {piece:<{inner}} |")
    out.append("+" + "-" * (width - 2) + "+")
    return "\n".join(out)


def render_events(events: list[Event]) -> str:
    rows = []
    for e in events:
        rows.append(f"{ICONS.get(e.kind, '[?]    ')} {e.title}")
        for line in e.lines:
            rows.extend(textwrap.wrap(line, WIDTH, initial_indent=" " * 10, subsequent_indent=" " * 10))
    return "\n".join(rows)


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = "|" + "|".join(f" {{:<{w}}} " for w in widths) + "|"
    return "\n".join([line, fmt.format(*headers), line, *(fmt.format(*map(str, r)) for r in rows), line])
