"""Instrumentation: wrap the model and the tools once, and every call becomes a span.

Wrapping at these two seams is the whole trick. The agent code stays clean; nobody can "forget"
to trace a call, because there is no untraced way to make one.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable

from .llm import LLM, Completion, Message
from .spans import Clock, Tracer

# USD per million tokens (input, output). Unknown models are priced at 0 and flagged.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "mock-llm": (4.00, 20.00),  # priced like claude-opus-5-5 so the demo shows realistic costs
}


class TracedLLM:
    def __init__(self, llm: LLM, tracer: Tracer) -> None:
        self.llm, self.tracer = llm, tracer
        self.name = llm.name

    def complete(self, system: str, messages: list[Message]) -> Completion:
        with self.tracer.span(f"llm {self.llm.name}", kind="llm", model=self.llm.name) as span:
            span.set("input.messages", len(messages))
            span.set("input.last", messages[-1]["content"])
            result = self.llm.complete(system, messages)
            price_in, price_out = PRICES.get(self.llm.name, (0.0, 0.0))
            span.set("usage.input_tokens", result.input_tokens)
            span.set("usage.output_tokens", result.output_tokens)
            span.set("cost_usd", round((result.input_tokens * price_in + result.output_tokens * price_out) / 1e6, 6))
            span.set("output.text", result.text)
            if self.llm.name not in PRICES:
                span.set("cost_note", "no price configured for this model")
            return result


class TracedTools:
    """A tool registry where every call is a span, including the failed ones."""

    def __init__(self, tracer: Tracer, clock: Clock) -> None:
        self.tracer, self.clock = tracer, clock
        self.search_attempts = 0
        self.handlers: dict[str, Callable[..., str]] = {
            "weather": self.weather, "calculator": self.calculator, "search": self.search,
        }

    def call(self, name: str, args: dict[str, Any]) -> str:
        with self.tracer.span(f"tool {name}", kind="tool", **{"tool.name": name, "tool.args": str(args)}) as span:
            if name not in self.handlers:
                raise KeyError(f"unknown tool {name!r}")
            result = self.handlers[name](**args)
            span.set("tool.result", result)
            return result

    def weather(self, city: str) -> str:
        self.clock.sleep(120)
        return f"weather: {city.title()} is 17C and cloudy"

    def calculator(self, expression: str) -> str:
        self.clock.sleep(2)
        return f"calculator: {expression} = {_safe_eval(expression):.2f}"

    def search(self, query: str) -> str:
        """Fails on the first attempt (a timeout), like real search APIs sometimes do."""
        self.search_attempts += 1
        if self.search_attempts == 1:
            self.clock.sleep(1500)
            raise TimeoutError("search backend did not answer within 1500 ms")
        self.clock.sleep(380)
        return f"search: 3 articles on {query}; top story says new sodium cells cut costs by 20%"


OPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
}


def _safe_eval(expression: str) -> float:
    """Arithmetic only. Never pass model output to eval()."""

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        raise ValueError(f"unsupported expression: {expression!r}")

    return walk(ast.parse(expression, mode="eval"))
