"""Watch a full MCP session on the wire: handshake, discovery, tool calls, resources, errors.

    python demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mcp_from_scratch.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["demo"]))
