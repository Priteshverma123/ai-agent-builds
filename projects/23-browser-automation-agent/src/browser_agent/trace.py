"""Terminal trace: plain ASCII boxes and aligned ``[tag   ]`` rows."""

from __future__ import annotations

import textwrap

WIDTH = 92


class Trace:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    def box(self, title: str, lines: list[str] | None = None) -> None:
        if self.quiet:
            return
        print("+" + "-" * (WIDTH - 2) + "+")
        for line in [title, *(lines or [])]:
            print(f"| {line[:WIDTH - 4]:<{WIDTH - 4}} |")
        print("+" + "-" * (WIDTH - 2) + "+")

    def row(self, tag: str, text: str) -> None:
        if self.quiet:
            return
        prefix = f"[{tag:<6}] "
        wrapped = textwrap.wrap(text, WIDTH - len(prefix)) or [""]
        print(prefix + wrapped[0])
        for line in wrapped[1:]:
            print(" " * len(prefix) + line)

    def snapshot(self, snapshot: str) -> None:
        """Show what the model sees, framed so it stands out from the trace."""
        lines = snapshot.splitlines()
        self.box("WHAT THE MODEL SEES: " + lines[0], lines[1:])
