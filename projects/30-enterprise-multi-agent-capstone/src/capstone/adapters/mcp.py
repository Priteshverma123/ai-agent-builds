"""A small MCP-style JSON-RPC 2.0 layer (recap of 08 and 09).

Server: `initialize`, `tools/list`, `tools/call`, with the standard JSON-RPC error codes.
Client: talks to any `Transport` (in-process, HTTP, or stdio) and never imports the tool code itself.
That boundary is the point: tools can live in another process, language or team.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

PROTOCOL_VERSION = "2025-06-18"
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict}


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def validate_args(schema: dict[str, Any], args: dict[str, Any]) -> None:
    """Just enough JSON Schema: required keys, known keys, primitive types."""
    props = schema.get("properties", {})
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        raise RpcError(INVALID_PARAMS, f"missing required argument(s): {', '.join(missing)}")
    for key, value in args.items():
        if key not in props:
            raise RpcError(INVALID_PARAMS, f"unknown argument '{key}'")
        expected = JSON_TYPES.get(props[key].get("type", ""), object)
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise RpcError(INVALID_PARAMS, f"argument '{key}' must be {props[key]['type']}")


class McpServer:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: dict[str, ToolDef] = {}

    def tool(self, name: str, description: str, input_schema: dict[str, Any]) -> Callable:
        """Decorator: @server.tool("search_docs", "...", {...schema...})."""
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = ToolDef(name, description, input_schema, fn)
            return fn
        return register

    def handle_raw(self, raw: str) -> str | None:
        """One JSON-RPC message in, one out (None for notifications)."""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps(self._error(None, PARSE_ERROR, "parse error"))
        response = self.handle(message)
        return None if response is None else json.dumps(response)

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return self._error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST,
                               "invalid request")
        msg_id, method, params = message.get("id"), message["method"], message.get("params") or {}
        if msg_id is None:  # notification, e.g. notifications/initialized
            return None
        try:
            return {"jsonrpc": "2.0", "id": msg_id, "result": self._dispatch(method, params)}
        except RpcError as exc:
            return self._error(msg_id, exc.code, exc.message)

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return {"protocolVersion": PROTOCOL_VERSION, "serverInfo": {"name": self.name, "version": "1.0.0"},
                    "capabilities": {"tools": {}}}
        if method == "tools/list":
            return {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                              for t in self.tools.values()]}
        if method == "tools/call":
            tool = self.tools.get(params.get("name", ""))
            if tool is None:
                raise RpcError(INVALID_PARAMS, f"unknown tool '{params.get('name')}'")
            args = params.get("arguments") or {}
            validate_args(tool.input_schema, args)
            try:
                result = tool.handler(**args)
            except Exception as exc:  # noqa: BLE001 - tool failures are results, not protocol errors
                return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}
        raise RpcError(METHOD_NOT_FOUND, f"method '{method}' not found")

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------- client side
class Transport(Protocol):
    def send(self, raw: str) -> str: ...


class InProcessTransport:
    def __init__(self, server: McpServer) -> None:
        self.server = server

    def send(self, raw: str) -> str:
        return self.server.handle_raw(raw) or ""


class HttpTransport:
    """POST each message to a /mcp endpoint. Works with httpx.Client or FastAPI's TestClient."""

    def __init__(self, client: Any, url: str = "/mcp") -> None:
        self.client, self.url = client, url

    def send(self, raw: str) -> str:
        r = self.client.post(self.url, content=raw, headers={"Content-Type": "application/json"})
        return r.text


class ToolError(Exception):
    """A tool ran and failed (isError) or the server returned a JSON-RPC error."""


class McpClient:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._next_id = 0
        self.server_info: dict[str, Any] = {}

    def _call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        raw = self.transport.send(json.dumps({"jsonrpc": "2.0", "id": self._next_id, "method": method,
                                              "params": params or {}}))
        reply = json.loads(raw)
        if "error" in reply:
            raise ToolError(f"rpc {reply['error']['code']}: {reply['error']['message']}")
        return reply["result"]

    def initialize(self) -> dict[str, Any]:
        self.server_info = self._call("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                                     "clientInfo": {"name": "capstone-orchestrator"}})
        return self.server_info

    def list_tools(self) -> list[dict[str, Any]]:
        return self._call("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        if result.get("isError"):
            raise ToolError(text)
        return json.loads(text)


class ScopedTools:
    """Least privilege: each specialist gets a view of the client restricted to its allow-list."""

    def __init__(self, client: McpClient, allowed: set[str]) -> None:
        self._client, self.allowed = client, allowed

    def call(self, name: str, **arguments: Any) -> Any:
        if name not in self.allowed:
            raise PermissionError(f"tool '{name}' is not on this agent's allow-list {sorted(self.allowed)}")
        return self._client.call_tool(name, arguments)
