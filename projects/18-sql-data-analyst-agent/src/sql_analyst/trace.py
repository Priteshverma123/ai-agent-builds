"""A tiny trace recorder and ASCII renderer - the part the video shows."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

WIDTH = 78


@dataclass
class Event:
    step: str
    lines: list[str]


@dataclass
class Tracer:
    """Collects what the agent did; ``echo=True`` prints each step as it happens."""

    echo: bool = False
    events: list[Event] = field(default_factory=list)

    def log(self, step: str, *lines: str) -> None:
        event = Event(step, [line for block in lines for line in block.splitlines()])
        self.events.append(event)
        if self.echo:
            print(step_line(event))

    def steps(self) -> list[str]:
        return [e.step for e in self.events]


def wrap(line: str, width: int) -> list[str]:
    """Wrap a long line but keep the indentation of short ones (SQL and code read better)."""
    if len(line) <= width:
        return [line]
    indent = line[: len(line) - len(line.lstrip())]
    return textwrap.wrap(line, width, subsequent_indent=indent) or [""]


def step_line(event: Event) -> str:
    """``  GUARD     | first line`` followed by indented continuation lines."""
    tag = f"  {event.step:<9}| "
    pad = " " * len(tag)
    out: list[str] = []
    for i, line in enumerate(event.lines or [""]):
        for j, chunk in enumerate(wrap(line, WIDTH - len(tag))):
            out.append((tag if i == 0 and j == 0 else pad) + chunk)
    return "\n".join(out)


def box(title: str, lines: list[str]) -> str:
    """Draw a titled ASCII box."""
    inner = WIDTH - 4
    top = f"+-- {title} " + "-" * max(0, WIDTH - len(title) - 6) + "+"
    body = [f"| {chunk.ljust(inner)} |" for line in lines for chunk in wrap(line, inner)]
    return "\n".join([top, *body, "+" + "-" * (WIDTH - 2) + "+"])
