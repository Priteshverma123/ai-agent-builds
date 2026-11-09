"""End-to-end: the demo story (CLI -> runner -> graders -> compare -> gate -> reports) and the CI subprocess."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from evalkit.cli import main
from evalkit.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("LLM_PROVIDER", "LLM_MODEL", "EVAL_SUITE", "EVAL_BASELINE", "EVAL_OUT_DIR", "EVAL_TRIALS",
            "AGENT_MAX_STEPS")


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EVAL_OUT_DIR", str(tmp_path / "out"))  # never write into the project folder


def test_story_passes_v1_and_blocks_v2(tmp_path, capsys):
    main([])
    out = capsys.readouterr().out
    v1, v2 = out.split("v2 (new prompt")
    assert "GATE: PASS (exit code 0)" in v1
    assert "GATE: REGRESSION (exit code 1)" in v2
    assert "3 case(s) regressed: refund_window, shipping_cost, broken_package" in v2
    assert "angry_customer          1.00  FIXED" in v2
    assert "would exit 1" in out
    results = json.loads((tmp_path / "out" / "results-v2.json").read_text(encoding="utf-8"))
    assert results["pass_rate"] == 0.7 and (tmp_path / "out" / "report-v1.md").exists()


def test_ci_mode_subprocess_exit_code(tmp_path):
    env = {**os.environ, "LLM_PROVIDER": "mock", "EVAL_OUT_DIR": str(tmp_path / "ci")}
    proc = subprocess.run([sys.executable, "demo.py", "run", "--agent", "v2"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1, proc.stderr
    assert "GATE: REGRESSION" in proc.stdout and (tmp_path / "ci" / "report-v2.md").exists()


def test_settings_read_from_env():
    s = Settings.from_env({"EVAL_TRIALS": "3", "EVAL_SUITE": "x.json", "LLM_PROVIDER": "OpenAI"})
    assert (s.trials, s.suite, s.llm_provider) == (3, Path("x.json"), "openai")
    assert Settings.from_env({}) == Settings()
