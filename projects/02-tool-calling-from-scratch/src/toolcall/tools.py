"""Turn plain Python functions into tools a model can call.

Three jobs, no framework:
1. Describe: build a JSON Schema from the function's signature and docstring.
2. Validate: check the model's arguments against that schema *before* running anything.
3. Dispatch: run the function and return the result (or the error) as text for the model.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

_JSON_TYPES: dict[type, str] = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass(frozen=True)
class ToolCall:
    """The model's request: 'please run `name` with these arguments'."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """What we send back. Errors are results too: the model can read them and recover."""

    call_id: str
    name: str
    ok: bool
    content: str


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # a JSON Schema "object"
    fn: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        """The provider-neutral definition: name + description + JSON Schema."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _arg_docs(fn: Callable[..., Any]) -> dict[str, str]:
    """Read 'name: description' lines from a Google-style 'Args:' docstring section."""
    doc = inspect.getdoc(fn) or ""
    section = doc.split("Args:", 1)[1] if "Args:" in doc else ""
    return dict(re.findall(r"^\s*(\w+): (.+)$", section, re.MULTILINE))


def schema_from_function(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema from type hints. The model never sees your code, only this."""
    hints = get_type_hints(fn)
    docs = _arg_docs(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        prop: dict[str, Any] = {"type": _JSON_TYPES[hints[name]]}
        if name in docs:
            prop["description"] = docs[name]
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _type_ok(value: Any, json_type: str) -> bool:
    if isinstance(value, bool):  # bool is a subclass of int in Python; JSON disagrees
        return json_type == "boolean"
    expected = {"string": str, "integer": int, "number": (int, float), "boolean": bool}[json_type]
    return isinstance(value, expected)


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    properties = schema["properties"]
    problems = [f"missing required argument '{n}'" for n in schema["required"] if n not in arguments]
    for name, value in arguments.items():
        if name not in properties:
            problems.append(f"unexpected argument '{name}'")
        elif not _type_ok(value, properties[name]["type"]):
            problems.append(f"'{name}' should be {properties[name]['type']}, got {type(value).__name__}")
    return problems


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator: @registry.register turns a typed, documented function into a tool."""
        description = (inspect.getdoc(fn) or fn.__name__).split("\n\n")[0]
        self._tools[fn.__name__] = Tool(fn.__name__, description, schema_from_function(fn), fn)
        return fn

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def call(self, call: ToolCall) -> ToolResult:
        """Validate, run, and package the result. Never raises: failures become error results."""
        tool = self._tools.get(call.name)
        if tool is None:
            return self._error(call, f"unknown tool '{call.name}'. Available: {', '.join(self._tools)}")
        problems = validate_arguments(tool.parameters, call.arguments)
        if problems:
            return self._error(call, "invalid arguments: " + "; ".join(problems))
        try:
            value = tool.fn(**call.arguments)
        except Exception as exc:  # the model should see the failure, not crash the loop
            return self._error(call, f"{type(exc).__name__}: {exc}")
        return ToolResult(call.id, call.name, ok=True, content=json.dumps(value))

    @staticmethod
    def _error(call: ToolCall, message: str) -> ToolResult:
        return ToolResult(call.id, call.name, ok=False, content=json.dumps({"error": message}))
