"""The agent's tools. In classic ReAct every tool takes one string and returns one string."""

from __future__ import annotations

import ast
import json
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "examples" / "knowledge.json"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[str], str]


class KnowledgeBase:
    """A tiny offline 'encyclopedia' with keyword search. Stands in for a search API."""

    def __init__(self, path: Path = KNOWLEDGE_FILE) -> None:
        self.articles: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))

    def search(self, query: str) -> str:
        words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for article in self.articles:
            title_words = set(re.findall(r"\w+", article["title"].lower()))
            text_words = set(re.findall(r"\w+", article["text"].lower()))
            score = 2 * len(words & title_words) + len(words & text_words)  # title hits count double
            if score:
                scored.append((score, article))
        if not scored:
            return f"No results for '{query}'."
        best = max(scored, key=lambda pair: pair[0])[1]
        return f"[{best['title']}] {best['text']}"


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> float:
    """Only numbers and + - * /. Never call eval() on model output."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("only numbers and + - * / are allowed")


def calculator(expression: str) -> str:
    try:
        result = _evaluate(ast.parse(expression.replace(",", ""), mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError) as exc:
        return f"Error: {exc}"
    return str(int(result) if float(result).is_integer() else round(result, 6))


def default_tools(kb: KnowledgeBase | None = None) -> dict[str, Tool]:
    kb = kb or KnowledgeBase()
    tools = [
        Tool("search", "Look up a topic in the encyclopedia. Input: a short topic name.", kb.search),
        Tool("calculator", "Evaluate arithmetic exactly. Input: an expression like 1937 - 1889.", calculator),
    ]
    return {tool.name: tool for tool in tools}
