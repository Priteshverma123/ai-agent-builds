import json

import pytest

from toolcall.agent import run
from toolcall.demo_tools import calculate, registry
from toolcall.llm import LLMResponse, MockLLM
from toolcall.tools import ToolCall, ToolRegistry, schema_from_function


def test_schema_is_built_from_type_hints_and_docstring():
    def book_table(restaurant: str, people: int, outdoor: bool = False) -> dict:
        """Book a table.

        Args:
            restaurant: Name of the restaurant.
            people: Party size.
        """
        return {}

    schema = schema_from_function(book_table)
    assert schema["properties"]["restaurant"] == {"type": "string", "description": "Name of the restaurant."}
    assert schema["properties"]["people"]["type"] == "integer"
    assert schema["properties"]["outdoor"] == {"type": "boolean"}
    assert schema["required"] == ["restaurant", "people"]  # outdoor has a default


@pytest.mark.parametrize(
    "call, expected_error",
    [
        (ToolCall("1", "fly_to_mars", {}), "unknown tool"),
        (ToolCall("2", "get_weather", {}), "missing required argument 'city'"),
        (ToolCall("3", "get_weather", {"city": 42}), "'city' should be string"),
        (ToolCall("4", "get_weather", {"city": "Paris", "units": "F"}), "unexpected argument 'units'"),
        (ToolCall("5", "get_weather", {"city": "Atlantis"}), "no weather data"),
    ],
)
def test_bad_calls_become_error_results_not_crashes(call, expected_error):
    result = registry.call(call)
    assert not result.ok
    assert expected_error in json.loads(result.content)["error"]


def test_good_call_returns_json():
    result = registry.call(ToolCall("1", "convert_currency", {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}))
    assert result.ok
    assert json.loads(result.content)["result"] == 92.0


def test_calculator_refuses_code():
    assert calculate("2 ** 10")["result"] == 1024
    for evil in ("__import__('os').system('echo hi')", "9 ** 9 ** 9"):
        with pytest.raises(ValueError):
            calculate(evil)


def test_full_loop_runs_parallel_tools_and_feeds_results_back():
    result = run("What's the weather in Paris and Tokyo?", MockLLM(), registry)
    assert result.rounds == 2
    assert [m["role"] for m in result.messages] == ["user", "assistant", "tool", "assistant"]
    assert len(result.messages[2]["results"]) == 2  # both results go back in one message
    assert "Paris: 18 C" in result.answer and "Tokyo: 24 C" in result.answer


def test_loop_stops_after_max_rounds():
    class Stubborn:
        """A model that never stops asking for tools."""

        def chat(self, system, messages, tools):
            return LLMResponse("", [ToolCall("x", "calculate", {"expression": "1+1"})])

    result = run("loop forever", Stubborn(), registry, max_rounds=3)
    assert result.rounds == 3
    assert "too many" in result.answer


def test_mock_only_calls_tools_it_was_offered():
    empty = ToolRegistry()
    result = run("What's the weather in Paris?", MockLLM(), empty)
    assert result.rounds == 1  # no tools offered -> no tool calls, just a reply
