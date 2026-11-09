"""The hub and the agent loop, end to end with MockLLM and real MCP subprocesses."""

from mcp_client_agent import MCPAgent, MCPHub, MockLLM, build_system_prompt
from mcp_client_agent.llm import ToolResult


def test_hub_namespaces_tools_from_two_servers(config_file):
    with MCPHub.from_config(config_file("work", "home")) as hub:
        names = {spec["name"] for spec in hub.tool_specs()}
        assert {"work__calculate", "home__calculate", "read_resource"} <= names
        hub.call("work__add_note", {"title": "only at work", "body": "x"})
        work = hub.call("work__search_notes", {"query": "only at work"})
        home = hub.call("home__search_notes", {"query": "only at work"})
        assert '"count": 1' in work.text and '"count": 0' in home.text  # separate processes, separate state


def test_hub_turns_failures_into_error_outcomes(config_file):
    with MCPHub.from_config(config_file("nb")) as hub:
        assert hub.call("nb__nope", {}).is_error
        assert hub.call("nb__calculate", {"expression": "1/0"}).is_error
        assert hub.call("read_resource", {"uri": "missing://x"}).is_error
        assert "Refunds" in hub.call("read_resource", {"uri": "docs://handbook"}).text


def test_agent_chains_resource_then_tool(config_file):
    with MCPHub.from_config(config_file("nb")) as hub:
        answer = MCPAgent(hub, MockLLM()).run("How many hours long is the refund window in our handbook policy?")
    assert answer == "The handbook gives a 30-day refund window, which is 720 hours."


def test_agent_recovers_from_tool_error(config_file):
    with MCPHub.from_config(config_file("nb")) as hub:
        assert MCPAgent(hub, MockLLM()).run("What is 17.5% of 2,340?") == "The answer is 409.5."


def test_mock_only_uses_discovered_tools():
    llm = MockLLM()
    llm.start("no resources", "What is 2 + 2?", tools=[{"name": "weather__forecast", "description": "",
                                                        "input_schema": {}}])
    assert llm.next_turn([]).answer == "I don't have a tool that can help with that."


def test_step_limit_stops_runaway_loops(config_file):
    class LoopingLLM(MockLLM):
        def next_turn(self, results: list[ToolResult]):
            return self._call("again", "nb__calculate", {"expression": "1+1"})

    with MCPHub.from_config(config_file("nb")) as hub:
        assert MCPAgent(hub, LoopingLLM(), max_steps=3).run("loop").startswith("Stopped after 3 steps")


def test_system_prompt_lists_servers_and_resources(config_file):
    with MCPHub.from_config(config_file("nb")) as hub:
        prompt = build_system_prompt(hub)
    assert "- nb: team-notebook 1.0.0" in prompt and "- docs://handbook:" in prompt
