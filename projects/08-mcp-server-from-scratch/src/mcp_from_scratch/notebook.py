"""The "team notebook" server: 4 tools and 3 resources on top of the MCP machinery.

Swap this file for your own domain (orders, tickets, a database) and the rest stays the same.
"""

from __future__ import annotations

import ast
import json
import operator
from pathlib import Path
from typing import Any

from .config import Settings
from .registry import ToolError
from .server import MCPServer

_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic without ``eval()``: walk the syntax tree and allow numbers and + - * / ** %."""

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolError("exponent too large")
            return _OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](walk(node.operand))
        raise ToolError(f"unsupported syntax: {ast.dump(node)[:40]}")

    try:
        tree = ast.parse(expression.replace(",", ""), mode="eval")
        return walk(tree.body)
    except SyntaxError as exc:
        raise ToolError(f"not a valid expression: {expression!r}") from exc
    except ZeroDivisionError as exc:
        raise ToolError("division by zero") from exc


def build_server(seed_file: Path | None = None, handbook: Path | None = None) -> MCPServer:
    """Build the team-notebook server. Paths default to ``Settings.from_env()`` (MCP_NOTES_FILE, MCP_HANDBOOK_FILE)."""
    settings = Settings.from_env()
    seed_file = seed_file or settings.notes_file
    handbook = handbook or settings.handbook_file
    server = MCPServer(
        name="team-notebook",
        version="1.0.0",
        instructions="Team notes and a handbook. Search notes before adding duplicates.",
    )
    notes: list[dict[str, Any]] = json.loads(seed_file.read_text(encoding="utf-8"))

    def find(note_id: int) -> dict[str, Any] | None:
        return next((n for n in notes if n["id"] == note_id), None)

    @server.tools.tool(title="Calculator", read_only=True)
    def calculate(expression: str) -> dict:
        """Evaluate an arithmetic expression exactly (use this instead of doing math in your head).

        Args:
            expression: Arithmetic using numbers, + - * / ** % and parentheses, e.g. "2340 * 0.175 + 12".
        """
        value = safe_eval(expression)
        return {"expression": expression, "result": round(value, 10)}

    @server.tools.tool(title="Add note")
    def add_note(title: str, body: str, tags: list[str] = []) -> dict:  # noqa: B006 (schema default)
        """Save a new note to the team notebook and return it with its id.

        Args:
            title: Short title for the note.
            body: The note text.
            tags: Optional lowercase tags, e.g. ["launch"].
        """
        note = {"id": max((n["id"] for n in notes), default=0) + 1, "title": title, "body": body,
                "tags": [t.lower() for t in tags]}
        notes.append(note)
        return note

    @server.tools.tool(title="Search notes", read_only=True)
    def search_notes(query: str, tag: str = "") -> dict:
        """Find notes whose title or body contains every word of the query (optionally filtered by tag).

        Args:
            query: Words to look for, case-insensitive.
            tag: Only return notes with this tag.
        """
        words = query.lower().split()
        hits = [n for n in notes
                if all(w in f"{n['title']} {n['body']} {' '.join(n['tags'])}".lower() for w in words)
                and (not tag or tag.lower() in n["tags"])]
        return {"query": query, "count": len(hits), "notes": hits}

    @server.tools.tool(title="Delete note", destructive=True)
    def delete_note(note_id: int) -> str:
        """Permanently delete a note by id.

        Args:
            note_id: The id returned by add_note or search_notes.
        """
        note = find(note_id)
        if note is None:
            raise ToolError(f"no note with id {note_id}")
        notes.remove(note)
        return f"Deleted note {note_id} ({note['title']})."

    server.resources.add(
        "docs://handbook", "Team handbook", "Policies: refunds, on-call, releases.", "text/markdown",
        lambda: handbook.read_text(encoding="utf-8"),
    )
    server.resources.add(
        "notes://index", "All notes", "Every note as JSON.", "application/json",
        lambda: json.dumps(notes, indent=2),
    )

    def read_note(note_id: str) -> str | None:
        note = find(int(note_id)) if note_id.isdigit() else None
        return json.dumps(note, indent=2) if note else None

    server.resources.add_template("note://{id}", "One note", "A single note by id.", "application/json", read_note)
    return server
