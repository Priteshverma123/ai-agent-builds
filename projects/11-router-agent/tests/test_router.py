import json

from conftest import ROOT
from router_agent import FALLBACK, Router, evaluate, load_labelled


def test_single_rule_hit_routes_without_calling_the_model(router):
    class ExplodingLLM:
        name = "boom"

        def complete(self, system, prompt):
            raise AssertionError("model should not be called")

    router.llm = ExplodingLLM()
    decision = router.route("Invoice INV-0977 looks wrong")
    assert (decision.intent, decision.method) == ("billing", "rule")


def test_llm_handles_messages_no_rule_covers(router):
    decision = router.route("How do I export my data to CSV?")
    assert (decision.intent, decision.method) == ("tech_support", "llm")
    assert decision.confidence >= router.threshold


def test_conflicting_rules_with_low_confidence_fall_back_with_candidates(router):
    decision = router.route("I can't log in and I also want a refund")
    assert decision.intent == FALLBACK
    assert decision.candidates == ["billing", "tech_support"]


def test_out_of_scope_message_falls_back(router):
    assert router.route("What's the weather in Paris?").intent == FALLBACK


class FixedLLM:
    name = "fixed"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, prompt):
        return self.reply


def test_invented_intent_or_garbage_output_falls_back():
    intents_router = Router.from_file(FixedLLM(json.dumps({"intent": "legal", "confidence": 0.99})),
                                      ROOT / "examples" / "intents.json")
    assert intents_router.route("hello there").intent == FALLBACK
    intents_router.llm = FixedLLM("I think it's billing!")
    assert intents_router.route("hello there").reason == "classifier returned unusable output"


def test_threshold_controls_fallback(router):
    router.threshold = 0.999
    assert router.route("My card payment keeps getting declined").intent == FALLBACK


def test_router_accuracy_on_labelled_set_does_not_regress(router):
    report = evaluate(router, load_labelled(ROOT / "examples" / "labelled.jsonl"))
    assert report.accuracy >= 0.9
