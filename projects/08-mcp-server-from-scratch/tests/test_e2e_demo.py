"""End-to-end: run demo.py (which spawns server.py) and the `serve` CLI exactly as a user would."""

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp_from_scratch import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}


def test_demo_walks_through_every_protocol_stage():
    out = subprocess.run([sys.executable, str(ROOT / "demo.py")], cwd=ROOT, env=ENV, capture_output=True,
                         text=True, encoding="utf-8", timeout=60, check=True).stdout
    for stage in ("1. HANDSHAKE", "2. DISCOVERY", "3. TOOL CALLS", "4. RESOURCES", "5. ERRORS"):
        assert stage in out
    assert "talking to team-notebook 1.0.0, protocol 2025-06-18" in out
    assert '"result": 421.5' in out
    assert "-32601 Method not found: prompts/list" in out
    assert "-32700" in out
    assert "Session closed: stdin EOF -> server exited cleanly" in out


def test_cli_serve_speaks_mcp_on_stdio():
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "calculate", "arguments": {"expression": "6*7"}}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in lines)
    code = "import sys; from mcp_from_scratch.cli import main; sys.exit(main(['serve']))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**ENV, "PYTHONPATH": str(ROOT / "src")},
                         input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=30, check=True).stdout
    replies = [json.loads(line) for line in out.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]  # the notification got no reply
    assert replies[1]["result"]["structuredContent"]["result"] == 42


def test_settings_point_at_seed_data_and_can_be_overridden(tmp_path):
    assert Settings.from_env({}).notes_file.name == "notes.json"
    assert Settings.from_env({"MCP_NOTES_FILE": str(tmp_path / "n.json")}).notes_file == tmp_path / "n.json"
