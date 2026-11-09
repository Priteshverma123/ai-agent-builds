"""The MCP server: a method router on top of JSON-RPC, plus a stdio loop.

``handle()`` is a pure "one message in, at most one message out" function. That keeps the
protocol logic testable without pipes, and lets the same object run over stdio or any
other transport.
"""

from __future__ import annotations

import sys
from typing import Any, Callable, TextIO

from .jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    encode,
    failure,
    is_notification,
    parse_line,
    success,
)
from .registry import ResourceRegistry, ToolRegistry

LATEST_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def log(message: str) -> None:
    """stdout belongs to the protocol. Anything human-readable goes to stderr."""
    print(f"[server] {message}", file=sys.stderr, flush=True)


class MCPServer:
    def __init__(self, name: str, version: str, instructions: str = "") -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        self.tools = ToolRegistry()
        self.resources = ResourceRegistry()
        self.protocol_version: str | None = None
        self.client_info: dict[str, Any] = {}
        self._methods: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "initialize": self._initialize,
            "ping": lambda params: {},
            "tools/list": lambda params: {"tools": self.tools.list()},
            "tools/call": self._call_tool,
            "resources/list": lambda params: {"resources": self.resources.list()},
            "resources/templates/list": lambda params: {"resourceTemplates": self.resources.list_templates()},
            "resources/read": self._read_resource,
        }

    # ---- lifecycle -------------------------------------------------------------------
    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise JsonRpcError(INVALID_PARAMS, "initialize needs a protocolVersion string")
        # Negotiation: echo the client's version if we speak it, otherwise offer our latest
        # and let the client decide whether to continue or disconnect.
        self.protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        self.client_info = params.get("clientInfo", {})
        log(f"initialize from {self.client_info.get('name', '?')} -> protocol {self.protocol_version}")
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": self.name, "version": self.version},
            "instructions": self.instructions,
        }

    # ---- features --------------------------------------------------------------------
    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "tools/call needs 'name' (string) and 'arguments' (object)")
        log(f"tools/call {name} {arguments}")
        return self.tools.call(name, arguments)

    def _read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise JsonRpcError(INVALID_PARAMS, "resources/read needs a 'uri' string")
        return self.resources.read(uri)

    # ---- dispatch --------------------------------------------------------------------
    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Process one decoded message. Returns the response, or None for notifications."""
        if is_notification(message):
            if message["method"] == "notifications/initialized":
                log("client says: initialized")
            return None  # notifications never get a reply, even unknown ones
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return failure(request_id, JsonRpcError(INVALID_REQUEST, "Invalid Request: missing method"))
        if self.protocol_version is None and method not in ("initialize", "ping"):
            return failure(request_id, JsonRpcError(INVALID_REQUEST, "Server not initialized: call initialize first"))
        handler = self._methods.get(method)
        if handler is None:
            return failure(request_id, JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}"))
        params = message.get("params") or {}
        try:
            return success(request_id, handler(params))
        except JsonRpcError as exc:
            return failure(request_id, exc)
        except Exception as exc:  # a bug in a handler must not kill the server
            log(f"internal error in {method}: {exc!r}")
            return failure(request_id, JsonRpcError(INTERNAL_ERROR, f"Internal error: {exc}"))

    def handle_line(self, line: str) -> str | None:
        """Decode, handle and encode one line of the stream."""
        try:
            message = parse_line(line)
        except JsonRpcError as exc:
            return encode(failure(None, exc))
        response = self.handle(message)
        return encode(response) if response is not None else None

    def serve_stdio(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        """Read newline-delimited JSON-RPC from stdin, write replies to stdout, until EOF."""
        if stdin is None:
            sys.stdin.reconfigure(encoding="utf-8")
            stdin = sys.stdin
        if stdout is None:
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # no \r\n on Windows
            stdout = sys.stdout
        log(f"{self.name} {self.version} ready on stdio")
        for line in stdin:
            if not line.strip():
                continue
            reply = self.handle_line(line)
            if reply is not None:
                stdout.write(reply + "\n")
                stdout.flush()
        log("stdin closed, shutting down")
