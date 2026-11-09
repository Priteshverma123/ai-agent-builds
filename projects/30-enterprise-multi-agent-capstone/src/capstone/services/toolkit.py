"""The company's tools, published on an MCP-style server (recap of 02, 05, 08, 14)."""
from __future__ import annotations

import ast
import itertools
import operator
import threading
from typing import Any

from capstone.adapters.mcp import McpServer
from capstone.services.rag import DocIndex

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expression: str) -> float:
    """Arithmetic only. eval() on model output is remote code execution; walking the AST is not."""
    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    if len(expression) > 200:
        raise ValueError("expression too long")
    return walk(ast.parse(expression, mode="eval"))


class TicketDesk:
    """Pretend ticketing system (the 'mutating' tool)."""

    def __init__(self) -> None:
        self.tickets: list[dict[str, Any]] = []
        self._ids = itertools.count(1001)
        self._lock = threading.Lock()

    def create(self, title: str, priority: str) -> dict[str, Any]:
        with self._lock:
            ticket = {"id": f"OPS-{next(self._ids)}", "title": title, "priority": priority, "status": "open"}
            self.tickets.append(ticket)
            return ticket


def build_tool_server(index: DocIndex, desk: TicketDesk) -> McpServer:
    server = McpServer("acme-tools")

    @server.tool("search_docs", "Search the company handbook. Returns cited passages.", {
        "type": "object", "required": ["query"],
        "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}})
    def search_docs(query: str, k: int = 3) -> list[dict[str, Any]]:
        return [{"id": h.chunk.id, "source": h.chunk.source, "section": h.chunk.section,
                 "text": h.chunk.text, "score": h.score} for h in index.search(query, k=min(max(k, 1), 5))]

    @server.tool("calculate", "Evaluate an arithmetic expression like '180 * 3'.", {
        "type": "object", "required": ["expression"], "properties": {"expression": {"type": "string"}}})
    def calculate(expression: str) -> dict[str, Any]:
        value = safe_eval(expression)
        return {"expression": expression, "value": round(value, 4)}

    @server.tool("create_ticket", "Open an Ops ticket. Side effect: creates a record.", {
        "type": "object", "required": ["title", "priority"],
        "properties": {"title": {"type": "string"}, "priority": {"type": "string"}}})
    def create_ticket(title: str, priority: str) -> dict[str, Any]:
        if priority not in ("low", "normal", "high"):
            raise ValueError("priority must be low, normal or high")
        return desk.create(title[:120], priority)

    return server
