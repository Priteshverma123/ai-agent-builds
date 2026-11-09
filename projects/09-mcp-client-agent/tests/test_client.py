"""The MCP client against the real project-08 server (and a server that never answers)."""

import sys

import pytest

from conftest import SERVER_08
from mcp_client_agent import MCPError, StdioMCPClient


def test_handshake_and_discovery():
    with StdioMCPClient("nb", [sys.executable, str(SERVER_08)]) as client:
        assert client.server_info["name"] == "team-notebook"
        assert client.protocol_version == "2025-06-18"
        assert {t["name"] for t in client.list_tools()} >= {"calculate", "search_notes"}
        assert client.list_resources()[0]["uri"] == "docs://handbook"
        result = client.call_tool("calculate", {"expression": "6 * 7"})
        assert result["structuredContent"]["result"] == 42


def test_protocol_errors_raise_mcp_error():
    with StdioMCPClient("nb", [sys.executable, str(SERVER_08)]) as client:
        with pytest.raises(MCPError) as info:
            client.request("prompts/list")
        assert info.value.code == -32601
        with pytest.raises(MCPError):
            client.read_resource("note://999")


def test_timeout_when_server_hangs(tmp_path):
    silent = tmp_path / "silent_server.py"
    silent.write_text("import sys, time\nfor line in sys.stdin:\n    time.sleep(30)\n", encoding="utf-8")
    client = StdioMCPClient("silent", [sys.executable, str(silent)], timeout=0.5).start()
    try:
        with pytest.raises(TimeoutError, match="no reply to initialize"):
            client.initialize()
    finally:
        client.close(grace=0.2)  # it ignores EOF while sleeping, so this ends in a kill
