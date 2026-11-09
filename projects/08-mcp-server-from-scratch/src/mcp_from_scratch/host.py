"""A minimal MCP *host* used by the demo: it launches the server and talks to it over pipes.

Project 09 builds the full client (timeouts, many servers, a real agent loop). This one is
deliberately tiny so the wire protocol stays in focus.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import trace

SERVER_SCRIPT = Path(__file__).resolve().parents[2] / "server.py"


class StdioConnection:
    """Spawn ``python server.py`` and exchange newline-delimited JSON-RPC with it."""

    def __init__(self, command: list[str] | None = None, show_wire: bool = True) -> None:
        self.process = subprocess.Popen(
            command or [sys.executable, str(SERVER_SCRIPT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.show_wire = show_wire
        self._next_id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        reply = json.loads(self.process.stdout.readline())
        if self.show_wire:
            trace.wire("<--", reply)
        return reply

    def notify(self, method: str) -> None:
        self.send({"jsonrpc": "2.0", "method": method})

    def send(self, message: dict[str, Any]) -> None:
        if self.show_wire:
            trace.wire("-->", message)
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def send_raw(self, line: str) -> dict[str, Any]:
        """Send bytes that are not valid JSON-RPC, to show how the server copes."""
        if self.show_wire:
            trace.row("-->", line)
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        if self.show_wire:
            trace.wire("<--", reply)
        return reply

    def close(self) -> None:
        self.process.stdin.close()  # EOF on stdin is how a stdio MCP server is told to stop
        self.process.wait(timeout=5)


class MockLLM:
    """Deterministic stand-in for the model: picks a tool *from the discovered list* by keywords."""

    RULES = [
        (r"[\d.,]+\s*[-+*/%]\s*[\d.,]+", "calculate"),
        (r"\b(remember|note that|save)\b", "add_note"),
        (r"\b(find|search|look up)\b", "search_notes"),
    ]

    def choose_tool(self, question: str, tools: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
        available = {t["name"] for t in tools}
        for pattern, name in self.RULES:
            if name in available and re.search(pattern, question, re.IGNORECASE):
                return name, self._arguments(name, question)
        return None

    @staticmethod
    def _arguments(name: str, question: str) -> dict[str, Any]:
        if name == "calculate":
            expression = re.search(r"[\d.,()\s+\-*/%]*\d[\d.,()\s+\-*/%]*", question).group(0).strip()
            return {"expression": expression}
        if name == "add_note":
            body = re.split(r"remember that|note that|save", question, flags=re.IGNORECASE)[-1].strip(" .")
            tags = re.findall(r"#(\w+)", body)
            body = re.sub(r"\s*#\w+", "", body)
            return {"title": body.split(",")[0][:40], "body": body, "tags": tags}
        query = re.split(r"find|search|look up", question, flags=re.IGNORECASE)[-1]
        query = re.sub(r"\b(notes?|my|about|for|the)\b", " ", query, flags=re.IGNORECASE)
        return {"query": " ".join(query.strip(" ?.").split())}
