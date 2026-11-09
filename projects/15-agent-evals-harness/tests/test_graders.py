import pytest
from pydantic import ValidationError

from evalkit.graders import contains, exact, json_fields, llm_judge, numeric, rubric
from evalkit.llm import MockJudgeLLM
from evalkit.suite import Suite


def test_exact_normalises_case_space_and_trailing_punctuation():
    assert exact("  Support@Shop.example. ", {"expected": "support@shop.example"}).passed
    assert not exact("support@shop.example is our email", {"expected": "support@shop.example"}).passed


def test_contains_scores_partially_and_enforces_forbidden_phrases():
    g = contains("Order 9999 shipped", {"all": ["couldn't find"], "none": ["shipped"]})
    assert g.score == 0.0 and not g.passed
    assert contains("We couldn't find it", {"all": ["couldn't find"], "none": ["shipped"]}).passed


def test_numeric_takes_the_answer_not_the_restated_question():
    assert numeric("Shipping for 3 items costs $7.99.", {"expected": 7.99, "tolerance": 0.01}).passed
    assert not numeric("Shipping for 3 items costs $9.49.", {"expected": 7.99, "tolerance": 0.01}).passed
    assert numeric("3 items, 7.99 total", {"expected": 3, "pick": "first"}).passed


def test_json_fields_handles_non_json_output():
    assert not json_fields("status: processing", {"expected": {"status": "processing"}}).passed
    g = json_fields('{"id": "1002", "status": "shipped"}', {"expected": {"id": "1002", "status": "processing"}})
    assert g.score == 0.5 and "status" in g.detail


def test_rubric_weights_and_threshold():
    params = {"pass_at": 0.8, "criteria": [
        {"name": "photo", "check": "contains", "arg": "photo", "weight": 3},
        {"name": "short", "check": "max_words", "arg": 3},
    ]}
    g = rubric("please send a photo of it", params)
    assert g.score == 0.75 and not g.passed and "short" in g.detail


class GarbageJudge:
    name = "garbage"

    def complete(self, system, messages):
        return "I think it's pretty good!"


def test_llm_judge_parses_scores_and_survives_garbage():
    params = {"key_points": ["sorry", "help"], "min_score": 4}
    good = llm_judge("I'm sorry, let me help.", params, MockJudgeLLM(), "q")
    assert good.passed and good.score == 1.0
    bad = llm_judge("Orders take a week.", params, MockJudgeLLM(), "q")
    assert not bad.passed and "misses" in bad.detail
    garbage = llm_judge("anything", params, GarbageJudge(), "q")
    assert not garbage.passed and "unparseable" in garbage.detail


def test_suite_validation_rejects_bad_suites():
    case = {"id": "a", "input": "q", "graders": [{"type": "exact", "params": {"expected": "x"}}]}
    with pytest.raises(ValidationError, match="duplicate"):
        Suite.model_validate({"name": "s", "version": "1", "cases": [case, case]})
    with pytest.raises(ValidationError):
        Suite.model_validate({"name": "s", "version": "1", "cases": [{**case, "graders": [{"type": "vibes"}]}]})
