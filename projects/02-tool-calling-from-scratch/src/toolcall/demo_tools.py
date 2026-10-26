"""Three example tools. Each is an ordinary, typed, documented Python function."""

from __future__ import annotations

import ast
import operator

from .tools import ToolRegistry

registry = ToolRegistry()

# Fake data keeps the demo offline and deterministic. Swap in a real API later.
_WEATHER = {
    "paris": (18, "cloudy"),
    "tokyo": (24, "sunny"),
    "mumbai": (31, "humid"),
    "london": (14, "light rain"),
}
_USD_RATES = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "INR": 83.1, "JPY": 151.4}


@registry.register
def get_weather(city: str) -> dict:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. "Paris".
    """
    key = city.strip().lower()
    if key not in _WEATHER:
        raise ValueError(f"no weather data for '{city}'")
    temp_c, conditions = _WEATHER[key]
    return {"city": city.title(), "temp_c": temp_c, "conditions": conditions}


@registry.register
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert money between currencies using today's rate.

    Args:
        amount: How much money to convert.
        from_currency: ISO code to convert from, e.g. "USD".
        to_currency: ISO code to convert to, e.g. "EUR".
    """
    src, dst = from_currency.upper(), to_currency.upper()
    for code in (src, dst):
        if code not in _USD_RATES:
            raise ValueError(f"unsupported currency '{code}'")
    rate = _USD_RATES[dst] / _USD_RATES[src]
    return {"amount": amount, "from": src, "to": dst, "rate": round(rate, 4), "result": round(amount * rate, 2)}


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> float:
    """Walk the syntax tree and allow only numbers and arithmetic. Never use eval() on model output."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")  # 9**9**9 would hang the process
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("only numbers and + - * / ** % are allowed")


@registry.register
def calculate(expression: str) -> dict:
    """Evaluate an arithmetic expression exactly.

    Args:
        expression: Arithmetic like "17 * 23 + 4".
    """
    result = _evaluate(ast.parse(expression, mode="eval").body)
    return {"expression": expression, "result": result}
