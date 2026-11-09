import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SERVER_08 = ROOT.parent / "08-mcp-server-from-scratch" / "server.py"


@pytest.fixture
def config_file(tmp_path):
    """Write a servers.json; pass several names to launch several copies of the project-08 server."""

    def make(*names: str) -> Path:
        path = tmp_path / "servers.json"
        servers = {name: {"command": "python", "args": [str(SERVER_08)]} for name in names}
        path.write_text(json.dumps({"servers": servers}), encoding="utf-8")
        return path

    return make
