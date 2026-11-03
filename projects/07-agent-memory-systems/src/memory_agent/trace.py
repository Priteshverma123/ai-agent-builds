"""A tiny terminal trace printer: ASCII boxes and tagged, aligned event lines.

The trace is the star of the demo: every thought, tool call and result is printed
so a learner can follow the agent step by step.
"""

from __future__ import annotations

import textwrap
from typing import Callable

WIDTH = 90


class Trace:
    """Collects and prints trace lines. Pass ``echo=False`` to keep it quiet (tests)."""

    def __init__(self, echo: bool = True, printer: Callable[[str], None] = print) -> None:
        self.echo = echo
        self.printer = printer
        self.lines: list[str] = []

    def _emit(self, line: str) -> None:
        self.lines.append(line)
        if self.echo:
            self.printer(line)

    def box(self, title: str, body: list[str] | None = None) -> None:
        """Print a framed box with a title and optional body lines."""
        inner = WIDTH - 4
        self._emit("+" + "-" * (WIDTH - 2) + "+")
        self._emit(f"| {title[:inner]:<{inner}} |")
        for raw in body or []:
            hang = "  " if raw.startswith("- ") else "    " if raw.startswith("[") else ""
            for line in textwrap.wrap(raw, inner, subsequent_indent=hang) or [""]:
                self._emit(f"| {line:<{inner}} |")
        self._emit("+" + "-" * (WIDTH - 2) + "+")

    def event(self, tag: str, text: str, details: list[str] | None = None) -> None:
        """Print ``[tag   ] text`` followed by indented detail lines."""
        first, *rest = textwrap.wrap(text, WIDTH - 9) or [""]
        self._emit(f"[{tag:<6}] {first}")
        for line in rest:
            self._emit(" " * 9 + line)
        for detail in details or []:
            for line in textwrap.wrap(detail, WIDTH - 9) or [""]:
                self._emit(" " * 9 + line)

    def blank(self) -> None:
        self._emit("")

    def text(self) -> str:
        return "\n".join(self.lines)
