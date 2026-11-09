"""Entry point for MCP clients:  python server.py   (speaks MCP on stdin/stdout)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mcp_from_scratch import build_server  # noqa: E402

if __name__ == "__main__":
    build_server().serve_stdio()
