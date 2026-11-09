"""End-to-end over real pipes, plus the schema builder on its own."""

from mcp_from_scratch import ToolRegistry, schema_from_signature
from mcp_from_scratch.host import MockLLM, StdioConnection


def test_full_session_over_stdio_subprocess():
    conn = StdioConnection(show_wire=False)
    try:
        init = conn.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "pytest", "version": "1"}})
        assert init["result"]["serverInfo"]["name"] == "team-notebook"
        conn.notify("notifications/initialized")
        tools = conn.request("tools/list")["result"]["tools"]
        name, args = MockLLM().choose_tool("What is (1 + 2) * 4?", tools)
        result = conn.request("tools/call", {"name": name, "arguments": args})["result"]
        assert result["structuredContent"]["result"] == 12
        assert conn.send_raw("not json")["error"]["code"] == -32700
        assert conn.request("ping")["result"] == {}  # still alive after garbage
    finally:
        conn.close()
    assert conn.process.returncode == 0  # EOF on stdin -> clean exit


def test_schema_from_signature_reads_types_defaults_and_docs():
    def book_room(room: str, people: int, projector: bool = False, notes: list[str] | None = None) -> str:
        """Book a meeting room.

        Args:
            room: Room name.
            people: How many people.
        """
        return room

    schema = schema_from_signature(book_room)
    assert schema["required"] == ["room", "people"]
    assert schema["properties"]["people"] == {"type": "integer", "description": "How many people."}
    assert schema["properties"]["projector"] == {"type": "boolean", "default": False}
    assert schema["properties"]["notes"]["type"] == "array"
    assert schema["additionalProperties"] is False


def test_registry_rejects_unknown_arguments():
    registry = ToolRegistry()

    @registry.tool(read_only=True)
    def echo(text: str) -> str:
        """Echo text back."""
        return text

    assert registry.call("echo", {"text": "hi"})["content"][0]["text"] == "hi"
    bad = registry.call("echo", {"text": "hi", "loud": True})
    assert bad["isError"] is True and "unknown argument 'loud'" in bad["content"][0]["text"]
