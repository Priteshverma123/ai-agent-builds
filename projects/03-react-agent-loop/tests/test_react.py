import pytest

from react_agent.agent import ReActAgent
from react_agent.llm import MockLLM, ScriptedLLM
from react_agent.parser import ParseError, parse
from react_agent.tools import KnowledgeBase, calculator, default_tools


def test_parser_reads_actions_and_final_answers():
    step = parse("Thought: look it up\nAction: search[Eiffel Tower]")
    assert (step.thought, step.action, step.action_input) == ("look it up", "search", "Eiffel Tower")
    assert parse("Thought: done\nFinal Answer: 48 years").final_answer == "48 years"


def test_parser_ignores_hallucinated_observations():
    step = parse("Thought: x\nAction: search[K2]\nObservation: K2 is 9000m\nFinal Answer: 9000m")
    assert step.action == "search" and step.final_answer is None


def test_parser_rejects_free_text():
    with pytest.raises(ParseError):
        parse("I think the answer is probably 42.")


def test_tools():
    assert calculator("1937 - 1889") == "48"
    assert calculator("8,849 - 8,611") == "238"
    assert calculator("__import__('os')").startswith("Error")
    assert "1889" in KnowledgeBase().search("Eiffel Tower")
    assert KnowledgeBase().search("Atlantis").startswith("No results")


def test_mock_agent_chains_search_search_calculate_answer():
    result = ReActAgent(MockLLM(), default_tools()).run(
        "How many years after the Eiffel Tower was completed did the Golden Gate Bridge open?"
    )
    assert result.stop_reason == "answered"
    assert result.answer == "48 years"
    assert [s.action for s in result.steps] == ["search", "search", "calculator", None]


def test_agent_admits_when_search_finds_nothing():
    result = ReActAgent(MockLLM(), default_tools()).run("What is the population of Atlantis?")
    assert "couldn't find" in (result.answer or "")


def test_step_limit_stops_a_model_that_never_answers():
    looping = ScriptedLLM(["Thought: hmm\nAction: search[Eiffel Tower]"])
    result = ReActAgent(looping, default_tools(), max_steps=3).run("anything")
    assert result.stop_reason == "max_steps"
    assert result.answer is None
    assert len(result.steps) == 3
    assert "already ran this exact action" in (result.steps[1].observation or "")


def test_bad_format_and_unknown_tool_become_observations_and_the_model_recovers():
    script = ScriptedLLM([
        "The answer is obviously 42.",
        "Thought: try a tool\nAction: wikipedia[K2]",
        "Thought: use the right tool\nAction: search[K2]",
        "Thought: got it\nFinal Answer: 8,611 metres",
    ])
    result = ReActAgent(script, default_tools()).run("How tall is K2?")
    assert result.answer == "8,611 metres"
    assert "Format error" in (result.steps[0].observation or "")
    assert "Unknown tool 'wikipedia'" in (result.steps[1].observation or "")
