"""Unified diff parsing and patch application.

A reviewer must comment on the *new* code at the *new* line numbers, and only on lines the
author actually changed. So we parse hunks into numbered lines, and we can rebuild the full
post-change file (base + patch) to run checks that need the whole file, like an AST.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """The diff does not apply to the base file (context lines differ)."""


@dataclass(frozen=True)
class Line:
    kind: str  # "+", "-" or " "
    text: str
    old_no: int | None
    new_no: int | None


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[Line] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: str | None  # None for a new file
    new_path: str | None  # None for a deleted file
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or "?"

    @property
    def is_new(self) -> bool:
        return self.old_path is None

    def added(self) -> dict[int, str]:
        """New line number -> text, for every added line."""
        return {ln.new_no: ln.text for h in self.hunks for ln in h.lines if ln.kind == "+" and ln.new_no}

    def stats(self) -> tuple[int, int]:
        lines = [ln for h in self.hunks for ln in h.lines]
        return sum(ln.kind == "+" for ln in lines), sum(ln.kind == "-" for ln in lines)


def _strip_prefix(path: str) -> str | None:
    path = path.split("\t")[0].strip()
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    old_no = new_no = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            current = FileDiff(_strip_prefix(line[4:]), _strip_prefix(lines[i + 1][4:]))
            files.append(current)
            hunk = None
            i += 2
            continue
        match = HUNK.match(line)
        if match and current is not None:
            old_start, old_len, new_start, new_len = (int(g) if g is not None else 1 for g in match.groups())
            hunk = Hunk(old_start, old_len, new_start, new_len)
            current.hunks.append(hunk)
            old_no, new_no = old_start, new_start
        elif hunk is not None and (line == "" or line[0] in "+- "):
            kind, body = (line[:1] or " "), line[1:]
            if kind == "+":
                hunk.lines.append(Line("+", body, None, new_no))
                new_no += 1
            elif kind == "-":
                hunk.lines.append(Line("-", body, old_no, None))
                old_no += 1
            else:
                hunk.lines.append(Line(" ", body, old_no, new_no))
                old_no += 1
                new_no += 1
        i += 1
    return files


def apply_patch(base: str, diff: FileDiff) -> str:
    """Rebuild the post-change file. Context and removed lines must match the base exactly."""
    old = base.splitlines()
    out: list[str] = []
    cursor = 0  # index into old
    for hunk in diff.hunks:
        start = hunk.old_start - 1 if hunk.old_len else hunk.old_start
        out.extend(old[cursor:start])
        cursor = start
        for ln in hunk.lines:
            if ln.kind in (" ", "-"):
                if cursor >= len(old) or old[cursor] != ln.text:
                    raise PatchError(f"{diff.path}: line {cursor + 1} does not match the diff context")
                cursor += 1
            if ln.kind in (" ", "+"):
                out.append(ln.text)
    out.extend(old[cursor:])
    return "\n".join(out) + "\n"
