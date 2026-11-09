"""Command-line entry: launch MCP servers, discover their tools, and let the agent use them.

    mcp-client-agent                           # servers from examples/servers.json
    mcp-client-agent --config my_servers.json  # your own servers
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .agent import MCPAgent
from .config import Settings
from .hub import MCPHub
from .llm import make_llm
from .trace import Trace


def show_discovery(hub: MCPHub, trace: Trace) -> None:
    """Print the handshake results and every tool/resource discovered at runtime."""
    lines = []
    for client in hub.clients.values():
        info = client.server_info
        lines.append(f"{client.name}: launched `{Path(client.command[-1]).name}` -> {info['name']} "
                     f"{info['version']}, protocol {client.protocol_version}")
    trace.box("1. LAUNCH + HANDSHAKE", lines)
    trace.box("2. RUNTIME DISCOVERY  (nothing about these tools is hard-coded in the agent)")
    for spec in hub.tool_specs():
        tool = hub.tools.get(spec["name"])
        kind = "built-in -> resources/read" if tool is None else (
            "read-only" if tool.read_only else "DESTRUCTIVE" if tool.destructive else "writes")
        params = ", ".join(spec["input_schema"]["properties"])
        trace.row("tool", f"{spec['name']:<24} ({params:<18}) {kind}")
    for resource in hub.resources:
        trace.row("res", f"{resource['uri']:<24} {resource['description']}")


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="An agent that gets its tools from MCP servers at runtime.")
    parser.add_argument("--config", type=Path, default=settings.servers_config,
                        help="servers.json to launch (default: $MCP_SERVERS_CONFIG or examples/servers.json)")
    parser.add_argument("--tasks", type=Path, default=settings.tasks_file, help="text file, one task per line")
    args = parser.parse_args(argv)
    trace = Trace()
    tasks = args.tasks.read_text(encoding="utf-8").splitlines()

    with MCPHub.from_config(args.config, timeout=settings.mcp_timeout) as hub:
        show_discovery(hub, trace)
        llm = make_llm(settings)
        agent = MCPAgent(hub, llm, max_steps=settings.max_steps, trace=trace)
        trace.box(f"3. AGENT RUNS  (model: {llm.name})")
        for task in tasks:
            agent.run(task)
            trace.blank()
    trace.box("Servers closed (stdin EOF). Try: python demo.py --config <your servers.json>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
