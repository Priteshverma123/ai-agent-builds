"""JSON-RPC 2.0: the envelope every MCP message travels in.

Three message shapes exist:
  request       {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {...}}
  notification  {"jsonrpc": "2.0", "method": "notifications/initialized"}      (no id, no reply)
  response      {"jsonrpc": "2.0", "id": 1, "result": {...}}  or  {..., "error": {...}}
"""

from __future__ import annotations

import json
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002  # MCP-specific code for resources/read


class JsonRpcError(Exception):
    """An error that becomes the ``error`` member of a JSON-RPC response."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def parse_line(line: str) -> dict[str, Any]:
    """Decode one line of the stdio stream into a message object."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {exc.msg}") from exc
    if not isinstance(message, dict):
        # Batches (JSON arrays) were removed from MCP in 2025-06-18, so we reject them.
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: expected a single JSON object")
    if message.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, 'Invalid Request: "jsonrpc" must be "2.0"')
    return message


def is_notification(message: dict[str, Any]) -> bool:
    return "method" in message and "id" not in message


def success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def failure(request_id: Any, error: JsonRpcError) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": error.to_dict()}


def encode(message: dict[str, Any]) -> str:
    """One message per line, no embedded newlines (the MCP stdio framing rule)."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))
