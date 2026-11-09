"""Protocol behaviour, tested in-process through ``MCPServer.handle_line`` (no pipes needed)."""

import json

import pytest

from mcp_from_scratch import build_server


def rpc(server, method, params=None, msg_id=1):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return json.loads(server.handle_line(json.dumps(message)))


@pytest.fixture
def server():
    s = build_server()
    rpc(s, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}})
    s.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
    return s


def test_initialize_negotiates_version():
    s = build_server()
    ok = rpc(s, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}})["result"]
    assert ok["protocolVersion"] == "2025-03-26"
    assert set(ok["capabilities"]) == {"tools", "resources"}
    future = rpc(build_server(), "initialize", {"protocolVersion": "2099-01-01", "capabilities": {}})["result"]
    assert future["protocolVersion"] == "2025-06-18"  # server offers its latest instead


def test_requests_before_initialize_are_rejected_but_ping_works():
    s = build_server()
    assert rpc(s, "tools/list")["error"]["code"] == -32600
    assert rpc(s, "ping")["result"] == {}


def test_notifications_get_no_reply(server):
    assert server.handle_line('{"jsonrpc":"2.0","method":"notifications/initialized"}') is None


def test_tools_list_has_schemas_and_hints(server):
    tools = {t["name"]: t for t in rpc(server, "tools/list")["result"]["tools"]}
    assert set(tools) == {"calculate", "add_note", "search_notes", "delete_note"}
    schema = tools["add_note"]["inputSchema"]
    assert schema["required"] == ["title", "body"]
    assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"},
                                            "description": 'Optional lowercase tags, e.g. ["launch"].', "default": []}
    assert tools["delete_note"]["annotations"]["destructiveHint"] is True
    assert tools["calculate"]["annotations"]["readOnlyHint"] is True


def test_tools_call_success_and_structured_content(server):
    result = rpc(server, "tools/call", {"name": "calculate", "arguments": {"expression": "2340 * 0.175 + 12"}})["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["result"] == 421.5


def test_tool_state_persists_between_calls(server):
    rpc(server, "tools/call", {"name": "add_note", "arguments": {"title": "Demo day", "body": "Friday", "tags": ["Launch"]}})
    found = rpc(server, "tools/call", {"name": "search_notes", "arguments": {"query": "demo", "tag": "launch"}})
    assert found["result"]["structuredContent"]["count"] == 1


def test_tool_errors_are_results_not_protocol_errors(server):
    bad_args = rpc(server, "tools/call", {"name": "calculate", "arguments": {"expression": 5}})["result"]
    assert bad_args["isError"] is True and "should be string" in bad_args["content"][0]["text"]
    unsafe = rpc(server, "tools/call", {"name": "calculate", "arguments": {"expression": "__import__('os')"}})["result"]
    assert unsafe["isError"] is True
    missing = rpc(server, "tools/call", {"name": "delete_note", "arguments": {"note_id": 99}})["result"]
    assert missing["isError"] is True and "no note with id 99" in missing["content"][0]["text"]


def test_unknown_tool_and_method_are_protocol_errors(server):
    assert rpc(server, "tools/call", {"name": "rm_rf", "arguments": {}})["error"]["code"] == -32602
    assert rpc(server, "sampling/createMessage")["error"]["code"] == -32601


def test_parse_errors_and_batches(server):
    assert json.loads(server.handle_line("{oops"))["error"]["code"] == -32700
    assert json.loads(server.handle_line("[]"))["error"]["code"] == -32600


def test_resources_list_read_and_templates(server):
    uris = [r["uri"] for r in rpc(server, "resources/list")["result"]["resources"]]
    assert uris == ["docs://handbook", "notes://index"]
    handbook = rpc(server, "resources/read", {"uri": "docs://handbook"})["result"]["contents"][0]
    assert handbook["mimeType"] == "text/markdown" and "30 days" in handbook["text"]
    templates = rpc(server, "resources/templates/list")["result"]["resourceTemplates"]
    assert templates[0]["uriTemplate"] == "note://{id}"
    note = json.loads(rpc(server, "resources/read", {"uri": "note://2"})["result"]["contents"][0]["text"])
    assert note["title"] == "Launch checklist"
    assert rpc(server, "resources/read", {"uri": "note://42"})["error"]["code"] == -32002
