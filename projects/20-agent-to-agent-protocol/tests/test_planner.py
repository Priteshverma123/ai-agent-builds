"""The planner end to end: discovery, routing, follow-ups and summary (MockLLM, in-process apps)."""

import json

from a2a_local import MockLLM, Planner


def test_planner_discovers_routes_and_answers_follow_up(fx, weather):
    planner = Planner([fx, weather], MockLLM())
    assert set(planner.discover()) == {"convert_currency", "packing_forecast"}
    answer = planner.run("I live in Toronto and I'm flying to Tokyo in April with 500 dollars. "
                         "What is that in yen, and what should I pack?")
    assert "500 CAD = 54,562 JPY" in answer
    assert "Tokyo in April: 19C / 10C" in answer and "umbrella" in answer


def test_planner_skips_skills_the_request_does_not_need(fx, weather):
    planner = Planner([fx, weather], MockLLM())
    planner.discover()
    answer = planner.run("I'm going to Lisbon in October. What should I pack?")
    assert "Lisbon in October" in answer and "JPY" not in answer and "EUR" not in answer


def test_planner_ignores_unknown_skills_from_the_model(fx):
    class ConfusedLLM(MockLLM):
        def complete(self, system, prompt):
            if "TASK: PLAN" in system:
                return json.dumps({"subtasks": [{"skill": "book_flight", "text": "Book LIS"}]})
            return super().complete(system, prompt)

    planner = Planner([fx], ConfusedLLM())
    assert planner.run("Book me a flight") == "None of my partner agents could help."


def test_mock_followup_does_not_invent_answers():
    reply = MockLLM().complete("TASK: FOLLOWUP", "Request: convert 5 dollars\nQuestion: Which dollars: USD, CAD, AUD?")
    assert reply.startswith("I don't know")
