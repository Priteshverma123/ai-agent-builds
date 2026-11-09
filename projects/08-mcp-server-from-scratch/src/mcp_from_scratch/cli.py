"""Command-line entry for the MCP server.

    mcp-notebook serve   # speak MCP on stdin/stdout (what Claude Desktop / project 09 launch)
    mcp-notebook demo    # launch `python server.py` as a subprocess and trace a full session
"""

from __future__ import annotations

import argparse
import json

from .host import MockLLM, StdioConnection
from .notebook import build_server
from .server import LATEST_PROTOCOL_VERSION
from .trace import box, row

QUESTIONS = [
    "What is 2340 * 0.175 + 12?",
    "Remember that the launch moved to Friday 14:00 #launch",
    "Find my notes about launch",
]


def run_demo() -> None:
    """Watch a full MCP session on the wire: handshake, discovery, tool calls, resources, errors."""
    conn = StdioConnection()
    llm = MockLLM()

    box("1. HANDSHAKE  (host launched `python server.py` as a subprocess)")
    init = conn.request("initialize", {
        "protocolVersion": LATEST_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "demo-host", "version": "0.1"},
    })["result"]
    conn.notify("notifications/initialized")
    row("ok", f"talking to {init['serverInfo']['name']} {init['serverInfo']['version']}, "
              f"protocol {init['protocolVersion']}, capabilities: {', '.join(init['capabilities'])}")

    box("2. DISCOVERY  (the host learns what the server can do at runtime)")
    tools = conn.request("tools/list")["result"]["tools"]
    for tool in tools:
        hint = "read-only" if tool["annotations"]["readOnlyHint"] else (
            "DESTRUCTIVE" if tool["annotations"]["destructiveHint"] else "writes")
        params = ", ".join(tool["inputSchema"]["properties"])
        row("tool", f"{tool['name']:<13} ({params:<18}) {hint:<11} {tool['description'][:30]}...")
    resources = conn.request("resources/list")["result"]["resources"]
    for resource in resources:
        row("res", f"{resource['uri']:<18} {resource['mimeType']:<18} {resource['description']}")

    box("3. TOOL CALLS  (MockLLM picks a tool from the discovered list)")
    for question in QUESTIONS:
        row("user", question)
        name, arguments = llm.choose_tool(question, tools)
        row("think", f"best tool: {name}  args: {arguments}")
        result = conn.request("tools/call", {"name": name, "arguments": arguments})["result"]
        shown = json.dumps(result["structuredContent"]) if "structuredContent" in result else result["content"][0]["text"]
        row("result", shown[:240])
        print()

    box("4. RESOURCES  (read-only context the host can pull in)")
    text = conn.request("resources/read", {"uri": "docs://handbook"})["result"]["contents"][0]["text"]
    row("read", text.split("## Refunds")[1].strip().splitlines()[0])
    conn.request("resources/read", {"uri": "note://4"})

    box("5. ERRORS  (protocol errors vs. tool errors the model can fix)")
    row("case", "bad arguments -> isError result, the model reads it and can retry")
    bad = conn.request("tools/call", {"name": "calculate", "arguments": {"expr": "1+1"}})["result"]
    row("model", f"isError={bad['isError']}: {bad['content'][0]['text']}")
    print()
    row("case", "unknown method -> JSON-RPC error -32601")
    error = conn.request("prompts/list")["error"]
    row("error", f"{error['code']} {error['message']}")
    print()
    row("case", "garbage on the wire -> JSON-RPC parse error -32700, server keeps running")
    error = conn.send_raw("{not json")["error"]
    row("error", f"{error['code']} {error['message']}")
    conn.request("ping")

    conn.close()
    box("Session closed: stdin EOF -> server exited cleanly", [
        "Plug the same server into Claude Desktop / Claude Code: see README 'Use a real LLM'."])



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-notebook", description="A Model Context Protocol server from scratch.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="serve MCP over stdio (stdout = protocol, stderr = logs)")
    sub.add_parser("demo", help="trace a full MCP session against server.py")
    args = parser.parse_args(argv)
    if args.command == "serve":
        build_server().serve_stdio()
    else:
        run_demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
