"""Run the tool server over stdio, one JSON-RPC message per line: python -m capstone.adapters.mcp_stdio

Any MCP-style client (like the one in project 09) can launch this process and discover the tools.
"""
from __future__ import annotations

import sys

from capstone.config import Settings
from capstone.services.rag import DocIndex
from capstone.services.toolkit import TicketDesk, build_tool_server


def main() -> None:
    server = build_tool_server(DocIndex.from_folder(Settings.from_env().docs_dir), TicketDesk())
    for line in sys.stdin:
        if line.strip():
            reply = server.handle_raw(line)
            if reply is not None:
                sys.stdout.write(reply + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
