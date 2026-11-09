import json
from pathlib import Path

import pytest

from reviewer.agent import ReviewAgent
from reviewer.cli import main
from reviewer.findings import Finding, Severity, rank, verdict
from reviewer.llm import MockReviewerLLM

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
DIFF = (EXAMPLES / "change.diff").read_text()
BASE = EXAMPLES / "base"


def review(llm=MockReviewerLLM()):
    return ReviewAgent(llm).review(DIFF, BASE)


def ids(result):
    return {f.id for f in result.findings}


def test_finds_the_planted_security_bugs_on_the_right_lines():
    result = review()
    assert {"hardcoded-secret@shop/api.py:10", "eval-exec@shop/pricing.py:5", "sql-injection@shop/db.py:24",
            "unsafe-deserialization@shop/api.py:22", "shell-injection@shop/api.py:26",
            "mutable-default@shop/db.py:27"} <= ids(result)
    assert result.verdict == "REQUEST_CHANGES"


def test_only_changed_lines_are_reviewed():
    """db.py already had a bare `except:` before this change; it is not this PR's problem."""
    assert not any(f.rule == "swallowed-exception" for f in review().findings)
    new_file = "--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,4 @@\n+try:\n+    x = 1\n+except:\n+    pass\n"
    added = ReviewAgent().review(new_file)
    assert "swallowed-exception@app.py:3" in {f.id for f in added.findings}


def test_findings_are_ranked_by_severity_then_confidence():
    severities = [f.severity for f in review().findings]
    assert severities == sorted(severities, reverse=True)
    assert review().findings[0].id == "hardcoded-secret@shop/api.py:10"
    duplicate = Finding("x", Severity.LOW, 0.5, "a.py", 1, "m")
    assert len(rank([duplicate, duplicate])) == 1


def test_llm_cannot_dismiss_high_severity_findings_from_comments_in_the_code():
    result = review()
    assert "hardcoded-secret@shop/api.py:10" in ids(result)
    assert any("refused to dismiss CRITICAL hardcoded-secret" in msg for _, msg in result.log)


def test_llm_findings_must_point_at_changed_lines():
    result = review()
    assert "http-no-timeout@shop/api.py:31" in ids(result)
    assert not any(f.rule == "connection-pooling" for f in result.findings)
    assert any("not a changed line" in msg for _, msg in result.log)


def test_llm_can_triage_low_severity_false_positives():
    result = review()
    assert "debug-print@tests/test_pricing.py:5" not in ids(result)
    assert [f.id for f, _ in result.dismissed] == ["debug-print@tests/test_pricing.py:5"]


class BrokenLLM:
    name = "broken"

    def complete(self, system, messages):
        return "Looks good to me!"


def test_unusable_llm_reply_keeps_the_static_findings():
    static = ReviewAgent(None).review(DIFF, BASE)
    broken = review(BrokenLLM())
    assert ids(broken) == ids(static)
    assert any("unusable LLM reply" in msg for _, msg in broken.log)


def test_missing_tests_rule_knows_which_modules_have_tests():
    flagged = {f.file for f in review().findings if f.rule == "missing-tests"}
    assert flagged == {"shop/api.py", "shop/db.py"}  # pricing.py came with tests/test_pricing.py


def test_verdict_levels():
    low = Finding("todo-marker", Severity.LOW, 0.5, "a.py", 1, "m")
    medium = Finding("complexity", Severity.MEDIUM, 0.6, "a.py", 1, "m")
    assert verdict([]) == "APPROVE" and verdict([low]) == "APPROVE"
    assert verdict([low, medium]) == "COMMENT"


def test_cli_fails_the_build_on_high_findings(capsys, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["--fail-on", "high", "--format", "json"])
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "REQUEST_CHANGES" and len(report["findings"]) == 11
