"""MCPHub: start every server in a config file and merge their tools into one namespaced catalogue.

Two servers may both have a ``search`` tool, so the model sees ``<server>__<tool>`` names and the
hub routes each call back to the right process. Resources are offered to the model through one
built-in tool, ``read_resource``, so it can pull in context when it decides it needs it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import MCPError, StdioMCPClient

SEPARATOR = "__"
READ_RESOURCE = "read_resource"


@dataclass
class RemoteTool:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    destructive: bool

    @property
    def qualified_name(self) -> str:
        return f"{self.server}{SEPARATOR}{self.name}"

    def spec(self) -> dict[str, Any]:
        """Provider-neutral tool definition handed to the LLM."""
        return {"name": self.qualified_name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class ToolOutcome:
    text: str
    is_error: bool


class MCPHub:
    def __init__(self, clients: list[StdioMCPClient]) -> None:
        self.clients = {c.name: c for c in clients}
        self.tools: dict[str, RemoteTool] = {}
        self.resources: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, path: Path, timeout: float = 10.0) -> "MCPHub":
        """Read ``{"servers": {"name": {"command": ..., "args": [...]}}}``. Relative paths are relative to the file."""
        config = json.loads(path.read_text(encoding="utf-8"))
        clients = []
        for name, entry in config["servers"].items():
            command = sys.executable if entry["command"] in ("python", "python3") else entry["command"]
            args = [str((path.parent / a).resolve()) if a.endswith(".py") else a for a in entry.get("args", [])]
            clients.append(StdioMCPClient(name, [command, *args], timeout=timeout))
        return cls(clients)

    def start(self) -> "MCPHub":
        """Launch, handshake and discover. Discovery happens at runtime: nothing is hard-coded."""
        for client in self.clients.values():
            client.start().initialize()
            for tool in client.list_tools():
                hints = tool.get("annotations", {})
                remote = RemoteTool(client.name, tool["name"], tool.get("description", ""), tool["inputSchema"],
                                    hints.get("readOnlyHint", False), hints.get("destructiveHint", True))
                self.tools[remote.qualified_name] = remote
            self.resources += [{**r, "server": client.name} for r in client.list_resources()]
        return self

    def close(self) -> None:
        for client in self.clients.values():
            client.close()

    def __enter__(self) -> "MCPHub":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def tool_specs(self) -> list[dict[str, Any]]:
        specs = [tool.spec() for tool in self.tools.values()]
        if self.resources:
            specs.append({
                "name": READ_RESOURCE,
                "description": "Read one of the resources listed in the system prompt by its URI.",
                "input_schema": {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]},
            })
        return specs

    def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        """Route a model's tool call to the owning server and flatten the result to text."""
        try:
            if name == READ_RESOURCE:
                return self._read_resource(arguments.get("uri", ""))
            tool = self.tools.get(name)
            if tool is None:
                return ToolOutcome(f"Unknown tool '{name}'. Available: {', '.join(self.tools)}", True)
            result = self.clients[tool.server].call_tool(tool.name, arguments)
        except (MCPError, TimeoutError, ConnectionError) as exc:
            return ToolOutcome(f"{type(exc).__name__}: {exc}", True)
        text = "\n".join(block.get("text", f"[{block['type']} content]") for block in result.get("content", []))
        return ToolOutcome(text, bool(result.get("isError")))

    def _read_resource(self, uri: str) -> ToolOutcome:
        owner = next((r["server"] for r in self.resources if r["uri"] == uri), None)
        servers = [owner] if owner else list(self.clients)  # templates (note://7) may live on any server
        for server in servers:
            try:
                contents = self.clients[server].read_resource(uri)["contents"]
                return ToolOutcome("\n".join(c.get("text", "") for c in contents), False)
            except MCPError:
                continue
        return ToolOutcome(f"Resource not found: {uri}", True)
