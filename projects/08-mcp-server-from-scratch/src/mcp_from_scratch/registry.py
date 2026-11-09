"""Tool and resource registries.

A tool is "a Python function + a JSON Schema + a few hints". We build the schema from the
function signature, so the code and the contract the model sees can never drift apart.
"""

from __future__ import annotations

import inspect
import json
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

from .jsonrpc import INVALID_PARAMS, RESOURCE_NOT_FOUND, JsonRpcError

JSON_TYPES: dict[type, str] = {str: "string", int: "integer", float: "number", bool: "boolean"}


class ToolError(Exception):
    """Raise inside a tool for an error the *model* should see and react to."""


def _json_type(annotation: Any) -> dict[str, Any]:
    """Map a Python type hint to a JSON Schema fragment."""
    if annotation in JSON_TYPES:
        return {"type": JSON_TYPES[annotation]}
    origin = typing.get_origin(annotation)
    if origin is list:
        (item,) = typing.get_args(annotation) or (str,)
        return {"type": "array", "items": _json_type(item)}
    if origin in (typing.Union, types.UnionType):
        options = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _json_type(options[0])
    raise TypeError(f"unsupported parameter type for a tool: {annotation!r}")


def _arg_docs(doc: str) -> dict[str, str]:
    """Read ``name: description`` lines from the ``Args:`` section of a docstring."""
    if "Args:" not in doc:
        return {}
    section = doc.split("Args:", 1)[1]
    return dict(re.findall(r"^\s+(\w+):\s*(.+)$", section, re.MULTILINE))


def schema_from_signature(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build an MCP ``inputSchema`` (a JSON Schema object) from a function signature."""
    hints = typing.get_type_hints(fn)
    docs = _arg_docs(inspect.getdoc(fn) or "")
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        prop = _json_type(hints[name])
        if name in docs:
            prop["description"] = docs[name]
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default
        properties[name] = prop
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """A tiny JSON Schema check: required keys, unknown keys and primitive types."""
    problems = [f"missing required argument '{name}'" for name in schema["required"] if name not in arguments]
    for name, value in arguments.items():
        prop = schema["properties"].get(name)
        if prop is None:
            problems.append(f"unknown argument '{name}'")
        elif not _matches(prop, value):
            problems.append(f"argument '{name}' should be {prop['type']}, got {type(value).__name__}")
    return problems


def _matches(prop: dict[str, Any], value: Any) -> bool:
    kind = prop["type"]
    if kind == "array":
        return isinstance(value, list) and all(_matches(prop["items"], v) for v in value)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, {"string": str, "boolean": bool}[kind])


@dataclass
class Tool:
    name: str
    title: str
    description: str
    handler: Callable[..., Any]
    input_schema: dict[str, Any]
    read_only: bool
    destructive: bool

    def describe(self) -> dict[str, Any]:
        """The entry this tool contributes to a ``tools/list`` result."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"readOnlyHint": self.read_only, "destructiveHint": self.destructive},
        }


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def tool(self, *, title: str = "", read_only: bool = False, destructive: bool = False) -> Callable:
        """Decorator: register a function as an MCP tool. The docstring's first paragraph is its description."""

        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            description = (inspect.getdoc(fn) or "").split("\n\n")[0].replace("\n", " ")
            self.tools[fn.__name__] = Tool(
                name=fn.__name__,
                title=title or fn.__name__.replace("_", " ").title(),
                description=description,
                handler=fn,
                input_schema=schema_from_signature(fn),
                read_only=read_only,
                destructive=destructive,
            )
            return fn

        return register

    def list(self) -> list[dict[str, Any]]:
        return [tool.describe() for tool in self.tools.values()]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run a tool and wrap the outcome as an MCP ``CallToolResult``.

        Unknown tool  -> protocol error (the client asked for something that does not exist).
        Bad arguments or a failing tool -> ``isError: true`` result, so the model can read it and retry.
        """
        tool = self.tools.get(name)
        if tool is None:
            raise JsonRpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        problems = validate_arguments(tool.input_schema, arguments)
        if problems:
            return error_result(f"Invalid arguments for {name}: " + "; ".join(problems))
        try:
            value = tool.handler(**arguments)
        except ToolError as exc:
            return error_result(str(exc))
        return ok_result(value)


def ok_result(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"content": [{"type": "text", "text": value}], "isError": False}
    text = json.dumps(value, ensure_ascii=False, indent=2)
    result = {"content": [{"type": "text", "text": text}], "isError": False}
    if isinstance(value, dict):
        result["structuredContent"] = value  # machine-readable twin of the text block
    return result


def error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {message}"}], "isError": True}


@dataclass
class Resource:
    uri: str
    name: str
    description: str
    mime_type: str
    read: Callable[[], str]


@dataclass
class ResourceTemplate:
    uri_template: str  # e.g. "note://{id}"
    name: str
    description: str
    mime_type: str
    read: Callable[[str], str | None]  # gets the {placeholder} value, returns None if missing

    def match(self, uri: str) -> str | None:
        prefix, _, suffix = self.uri_template.partition("{")
        suffix = suffix.split("}", 1)[1]
        if uri.startswith(prefix) and uri.endswith(suffix) and len(uri) > len(prefix) + len(suffix):
            return uri[len(prefix): len(uri) - len(suffix)]
        return None


@dataclass
class ResourceRegistry:
    resources: dict[str, Resource] = field(default_factory=dict)
    templates: list[ResourceTemplate] = field(default_factory=list)

    def add(self, uri: str, name: str, description: str, mime_type: str, read: Callable[[], str]) -> None:
        self.resources[uri] = Resource(uri, name, description, mime_type, read)

    def add_template(self, uri_template: str, name: str, description: str, mime_type: str,
                     read: Callable[[str], str | None]) -> None:
        self.templates.append(ResourceTemplate(uri_template, name, description, mime_type, read))

    def list(self) -> list[dict[str, Any]]:
        return [{"uri": r.uri, "name": r.name, "description": r.description, "mimeType": r.mime_type}
                for r in self.resources.values()]

    def list_templates(self) -> list[dict[str, Any]]:
        return [{"uriTemplate": t.uri_template, "name": t.name, "description": t.description,
                 "mimeType": t.mime_type} for t in self.templates]

    def read(self, uri: str) -> dict[str, Any]:
        if uri in self.resources:
            resource = self.resources[uri]
            return {"contents": [{"uri": uri, "mimeType": resource.mime_type, "text": resource.read()}]}
        for template in self.templates:
            value = template.match(uri)
            if value is not None and (text := template.read(value)) is not None:
                return {"contents": [{"uri": uri, "mimeType": template.mime_type, "text": text}]}
        raise JsonRpcError(RESOURCE_NOT_FOUND, "Resource not found", {"uri": uri})
