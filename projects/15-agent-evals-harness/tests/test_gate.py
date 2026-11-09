import json
from pathlib import Path

import pytest

from evalkit.agent import SupportAgent
from evalkit.cli import main
from evalkit.compare import Exit, gate
from evalkit.llm import MockJudgeLLM, MockSupportLLM
from evalkit.runner import RunResult, run_suite
from evalkit.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = load_suite(ROOT / "examples" / "support_suite.json")
BASELINE = RunResult.from_dict(json.loads((ROOT / "examples" / "baseline.json").read_text()))


def run(version: str) -> RunResult:
    return run_suite(SUITE, SupportAgent(MockSupportLLM(version)), MockJudgeLLM())


def test_released_version_matches_its_baseline():
    result = gate(run("v1"), BASELINE, SUITE.pass_threshold)
    assert result.exit is Exit.OK
    assert result.comparison.regressions == [] and result.comparison.score_delta == 0


def test_regressions_fail_the_run_even_when_something_improved():
    result = gate(run("v2"), BASELINE, SUITE.pass_threshold)
    assert result.exit is Exit.REGRESSION
    assert result.comparison.regressions == ["refund_window", "shipping_cost", "broken_package"]
    assert result.comparison.fixes == ["angry_customer"]


def test_without_baseline_the_absolute_threshold_still_gates():
    assert gate(run("v2"), None, pass_threshold=0.8).exit is Exit.BELOW_THRESHOLD
    assert gate(run("v1"), None, pass_threshold=0.8).exit is Exit.OK


@pytest.mark.parametrize("version, code", [("v1", 0), ("v2", 1)])
def test_cli_exit_codes_for_ci(version, code, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)  # tests always use the offline mock
    with pytest.raises(SystemExit) as exc:
        main(["run", "--agent", version, "--out", str(tmp_path)])
    assert exc.value.code == code
    assert (tmp_path / f"report-{version}.md").exists()


class CoinFlipLLM:
    """Answers correctly every other call: the kind of flakiness repeated trials expose."""

    name = "mock:flaky"

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages):
        self.calls += 1
        hours = "9am-5pm" if self.calls % 2 else "whenever"
        return json.dumps({"answer": f"Support is open {hours}."})


def test_repeated_trials_expose_flaky_cases():
    suite = SUITE.model_copy(update={"cases": [c for c in SUITE.cases if c.id == "opening_hours"]})
    result = run_suite(suite, SupportAgent(CoinFlipLLM()), MockJudgeLLM(), trials=4)
    case = result.cases[0]
    assert case.flaky and not case.passed and case.pass_count == 2 and case.score == 0.5
