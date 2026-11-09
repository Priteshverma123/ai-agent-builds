"""Launch the MCP server from project 08, discover its tools, and let the agent use them.

    python demo.py                              # servers from examples/servers.json
    python demo.py --config my_servers.json     # your own servers
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mcp_client_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
