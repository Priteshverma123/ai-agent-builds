"""A Model Context Protocol server written from scratch (stdlib only)."""

__version__ = "1.0.0"

from .config import Settings
from .jsonrpc import JsonRpcError
from .notebook import build_server
from .registry import ToolError, ToolRegistry, schema_from_signature
from .server import LATEST_PROTOCOL_VERSION, MCPServer

__all__ = ["JsonRpcError", "LATEST_PROTOCOL_VERSION", "MCPServer", "Settings", "ToolError", "ToolRegistry",
           "build_server", "schema_from_signature"]
