from support_agent.evals import EvalResult, check, format_report, run_suite
from support_agent.services.agent import TurnResult


def test_full_eval_suite_passes(settings):
    results = run_suite(settings)
    failed = {r.case_id: r.failures for r in results if not r.passed}
    assert len(results) >= 12 and failed == {}


def test_checker_reports_each_broken_expectation():
    result = TurnResult("c", "Sure thing", "t")
    failures = check({"tools_include": ["get_order"], "escalated": True, "reply_contains": ["refund"],
                      "min_citations": 1, "refund_status": "approved"}, [result])
    assert len(failures) == 5


def test_report_shows_pass_rate():
    report = format_report([EvalResult("a", True), EvalResult("b", False, ["boom"])])
    assert "1/2 passed (50%)" in report and "boom" in report
