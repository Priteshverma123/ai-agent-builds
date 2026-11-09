"""End-to-end: the demo flow (both scripted debates, judged) runs exactly as a learner runs it."""

import os
import subprocess
import sys
from pathlib import Path

from debate.cli import main
from debate.config import Settings, load_settings
from debate.llm import MockDebateLLM, llm_from_env

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script_runs_both_debates_offline():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline MockLLM
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.count("+-- DEBATE") == 2 and out.count("+-- JUDGE") == 2
    assert "CONSENSUS:" in out and "NO CONSENSUS" in out
    assert "possible herding" in out


def test_cli_threshold_comes_from_settings(monkeypatch, capsys):
    monkeypatch.setenv("CONSENSUS_THRESHOLD", "0.99")  # nothing is unanimous enough now
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert out.count("NO CONSENSUS") == 2


def test_settings_from_env():
    assert load_settings({}) == Settings()
    s = load_settings({"LLM_PROVIDER": "Anthropic", "DEBATE_MAX_ROUNDS": "2", "LLM_MODEL": ""})
    assert (s.llm_provider, s.llm_model, s.max_rounds, s.use_mock) == ("anthropic", None, 2, False)
    mock = MockDebateLLM(Settings().script_path)
    assert llm_from_env(mock, Settings()) is mock
