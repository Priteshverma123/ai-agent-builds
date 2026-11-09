"""End-to-end: run the real demo flow (CLI -> scenarios -> agent -> guards) and check the story it tells."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from guardrails.cli import main
from guardrails.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "GUARD_THRESHOLD", "AGENT_MAX_STEPS", "EXAMPLES_DIR"):
        monkeypatch.delenv(name, raising=False)


def test_full_demo_shows_leak_then_every_defence(capsys):
    main([])
    out = capsys.readouterr().out
    assert out.count(">>> LEAK: email sent to attacker@evil.example") == 1  # only scenario 1 leaks
    assert out.count(">>> SAFE: no email left the building.") == 2
    assert "injection quarantined" in out
    assert "recipient domain 'evil.example' is not on the email allow-list" in out
    assert "[REDACTED:aws_access_key]" in out and "AKIA" not in out.split("4a. Output guard")[1]
    assert "input guard refused the request" in out
    assert "attacks caught 14/14   false positives 0   known gaps missed 1" in out


def test_single_scenario_flag(capsys):
    main(["--scenario", "3"])
    out = capsys.readouterr().out
    assert "3. Detector fooled, policy still holds" in out and "1. NO guardrails" not in out


def test_demo_script_runs_as_a_subprocess():
    env = {**os.environ, "LLM_PROVIDER": "mock"}
    proc = subprocess.run([sys.executable, "demo.py", "--scenario", "2"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert ">>> SAFE: no email left the building." in proc.stdout


def test_settings_read_from_env():
    s = Settings.from_env({"LLM_PROVIDER": " Anthropic ", "GUARD_THRESHOLD": "0.7", "AGENT_MAX_STEPS": "3"})
    assert (s.llm_provider, s.guard_threshold, s.max_steps) == ("anthropic", 0.7, 3)
    assert Settings.from_env({}) == Settings()
