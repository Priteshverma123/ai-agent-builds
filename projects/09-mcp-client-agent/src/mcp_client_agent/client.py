"""An MCP client for stdio servers: launch, handshake, request/response matching, timeouts.

A background thread reads the server's stdout. Every response is routed back to the
caller waiting on that request id, so several calls can be in flight at once. Messages
*from* the server (notifications, or requests like ``ping``) are handled on the same thread.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from collections import deque
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


class MCPError(Exception):
    """The server answered with a JSON-RPC error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class StdioMCPClient:
    def __init__(self, name: str, command: list[str], cwd: str | None = None, timeout: float = 10.0) -> None:
        self.name = name
        self.command = command
        self.cwd = cwd
        self.timeout = timeout
        self.server_info: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}
        self.instructions = ""
        self.protocol_version = ""
        self.notifications: list[dict[str, Any]] = []
        self.stderr_tail: deque[str] = deque(maxlen=50)
        self._pending: dict[int, queue.Queue] = {}
        self._next_id = 0
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    # ---- process ---------------------------------------------------------------------
    def start(self) -> "StdioMCPClient":
        self._process = subprocess.Popen(
            self.command, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        return self

    def close(self, grace: float = 3.0) -> None:
        """Close stdin (the stdio way to say goodbye), then kill the server if it ignores that for ``grace`` s."""
        if self._process is None:
            return
        try:
            self._process.stdin.close()
            self._process.wait(timeout=grace)
        except (OSError, subprocess.TimeoutExpired):
            self._process.kill()
        self._process = None

    def __enter__(self) -> "StdioMCPClient":
        return self.start().initialize()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- JSON-RPC --------------------------------------------------------------------
    def _write(self, message: dict[str, Any]) -> None:
        if self._process is None or self._process.poll() is not None:
            raise ConnectionError(f"server '{self.name}' is not running")
        with self._lock:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
        inbox: queue.Queue = queue.Queue(maxsize=1)
        self._pending[request_id] = inbox
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        try:
            reply = inbox.get(timeout=timeout or self.timeout)
        except queue.Empty:
            # Tell the server to stop working on it, then give up.
            self.notify("notifications/cancelled", {"requestId": request_id, "reason": "client timeout"})
            raise TimeoutError(f"{self.name}: no reply to {method} within {timeout or self.timeout}s") from None
        finally:
            self._pending.pop(request_id, None)
        if "error" in reply:
            raise MCPError(reply["error"]["code"], reply["error"]["message"])
        return reply["result"]

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params
        self._write(message)

    def _read_stdout(self) -> None:
        for line in self._process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.stderr_tail.append(f"(non-JSON on stdout) {line.strip()}")
                continue
            if "method" not in message:  # a response to one of our requests
                inbox = self._pending.get(message.get("id"))
                if inbox is not None:
                    inbox.put(message)
            elif "id" in message:  # the server is asking *us* something
                self._answer_server_request(message)
            else:  # a notification, e.g. notifications/tools/list_changed
                self.notifications.append(message)

    def _answer_server_request(self, message: dict[str, Any]) -> None:
        if message["method"] == "ping":
            self._write({"jsonrpc": "2.0", "id": message["id"], "result": {}})
        else:  # we declared no client capabilities (roots, sampling, elicitation)
            self._write({"jsonrpc": "2.0", "id": message["id"],
                         "error": {"code": -32601, "message": f"Method not found: {message['method']}"}})

    def _read_stderr(self) -> None:
        for line in self._process.stderr:
            self.stderr_tail.append(line.rstrip())

    # ---- MCP -------------------------------------------------------------------------
    def initialize(self) -> "StdioMCPClient":
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-client-agent", "version": "1.0.0"},
        })
        if result["protocolVersion"] not in SUPPORTED_VERSIONS:
            self.close()
            raise MCPError(-32600, f"unsupported protocol version {result['protocolVersion']}")
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        self.instructions = result.get("instructions", "")
        self.protocol_version = result["protocolVersion"]
        self.notify("notifications/initialized")
        return self

    def _paginate(self, method: str, key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = None
        while True:
            result = self.request(method, {"cursor": cursor} if cursor else {})
            items.extend(result.get(key, []))
            cursor = result.get("nextCursor")
            if not cursor:
                return items

    def list_tools(self) -> list[dict[str, Any]]:
        return self._paginate("tools/list", "tools") if "tools" in self.capabilities else []

    def list_resources(self) -> list[dict[str, Any]]:
        return self._paginate("resources/list", "resources") if "resources" in self.capabilities else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self.request("resources/read", {"uri": uri})
